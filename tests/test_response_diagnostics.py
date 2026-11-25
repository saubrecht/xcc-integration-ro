"""Controller diagnostics, runnable with the Python standard library only."""

import ast
import asyncio
import importlib.util
import logging
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock

XCC = Path(__file__).resolve().parents[1] / "custom_components/xcc"
spec = importlib.util.spec_from_file_location("_response_diagnostics", XCC / "response_diagnostics.py")
diagnostics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostics)


class TestStatusBody(unittest.TestCase):
    def test_valid_xml_does_not_log_values(self):
        raw = b'<PAGE><INPUT P="SVENKU" VALUE="private-value"/></PAGE>'
        result = diagnostics.diagnose_status_body(raw, 200, [])
        self.assertTrue(result["valid"])
        self.assertNotIn("private-value", result["preview"])

    def test_empty_html_login_and_non_data_xml_are_rejected(self):
        for raw, status in [
            (b'', 200), (b'  ', 200), (b'<!DOCTYPE html><html><title>Error</title></html>', 200),
            (b'<PAGE><LOGIN/><INPUT P="X" VALUE="1"/></PAGE>', 200),
            (b'<PAGE/>', 200), (b'<PAGE>', 200),
            (b'<PAGE><INPUT P="X" VALUE="1"/></PAGE>', 500),
            (b'<PAGE><INPUT P="X" VALUE="1"/></PAGE>', 302),
        ]:
            with self.subTest(raw=raw, status=status):
                self.assertFalse(diagnostics.diagnose_status_body(raw, status, [])["valid"])

    def test_preview_preserves_error_but_removes_credentials(self):
        raw = b'''<!DOCTYPE html><html><title>Access denied</title><body>
        password=unknown-secret SoftPLC=unknown-cookie
        <input value="form-secret" name="password">
        <script>var token="script-secret"</script>
        <textarea>textarea-secret</textarea>
        known-password known-cookie
        </body></html>'''
        result = diagnostics.diagnose_status_body(raw, 200, ["known-password", "known-cookie"])
        self.assertEqual(result["kind"], "html")
        self.assertIn("Access denied", result["preview"])
        for secret in ["unknown-secret", "unknown-cookie", "form-secret", "script-secret",
                       "textarea-secret", "known-password", "known-cookie"]:
            self.assertNotIn(secret, result["preview"])

    def test_encoded_form_values_are_not_logged(self):
        raw = b'<html><input value="hidden-token"><p>known&#45;password</p></html>'
        result = diagnostics.diagnose_status_body(raw, 200, ["known-password"])
        self.assertNotIn("hidden-token", result["preview"])
        self.assertNotIn("known-password", result["preview"])

    def test_windows_encoding_and_bounded_preview(self):
        raw = '<html><title>Přístup odepřen</title></html>'.encode('cp1250')
        result = diagnostics.diagnose_status_body(raw, 200, [], 'windows-1250')
        self.assertIn('Přístup odepřen', result['preview'])
        self.assertLessEqual(len(diagnostics.diagnose_status_body(b'x' * 10000, 200, [])['preview']), 800)

    def test_url_omits_credentials_and_query(self):
        self.assertEqual(diagnostics.safe_url('http://user:secret@192.0.2.1/LOGIN.XML?token=secret#fragment'),
                         'http://192.0.2.1/LOGIN.XML')


class TestDirectProbe(unittest.IsolatedAsyncioTestCase):
    """Load the actual transport method without importing HA/aiohttp.

    Only its HTTP session is replaced; redirects, retries and logging are
    exercised by the production method using the standard-library helpers.
    """

    def setUp(self):
        tree = ast.parse((XCC / 'xcc_client.py').read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'XCCClient')
        methods = [
            node for node in cls.body if isinstance(node, ast.AsyncFunctionDef)
            and node.name in {"probe_status", "ensure_status_session"}
        ]
        rejected = next(
            node for node in tree.body if isinstance(node, ast.ClassDef)
            and node.name == "StatusSessionRejected"
        )
        package = types.ModuleType('_xcc_probe_test')
        package.__path__ = []
        sys.modules[package.__name__] = package
        sys.modules[package.__name__ + '.response_diagnostics'] = diagnostics
        self.addCleanup(sys.modules.pop, package.__name__, None)
        self.addCleanup(sys.modules.pop, package.__name__ + '.response_diagnostics', None)
        # Use the production import instead of injecting logging, which hid a
        # missing module import in the original diagnostic implementation.
        imports = [
            node for node in tree.body if isinstance(node, ast.Import)
            and any(alias.name == 'logging' for alias in node.names)
        ]
        self.timeout = Mock()
        self.ns = {
            "__package__": package.__name__, "__name__": package.__name__,
            "asyncio": asyncio, "_auth_locks": {}, "DEFAULT_TIMEOUT": 10,
            "aiohttp": types.SimpleNamespace(ClientTimeout=self.timeout),
        }
        exec(compile(ast.Module(body=[*imports, rejected, *methods], type_ignores=[]),
                     "xcc_client.py", "exec"), self.ns)

    async def test_probe_uses_one_get_and_redacts_rejected_reply(self):
        raw = b'<html><title>Access denied</title><input value="cookie-secret">password-secret</html>'
        response = types.SimpleNamespace(
            status=200, charset='utf-8', url='http://192.0.2.1/STATUS.XML?token=cookie-secret',
            headers={'Content-Type': 'text/html', 'Location': '/LOGIN.XML?token=cookie-secret'},
            read=AsyncMock(return_value=raw),
        )
        cm = Mock()
        cm.__aenter__ = AsyncMock(return_value=response)
        cm.__aexit__ = AsyncMock(return_value=False)
        session = types.SimpleNamespace(get=Mock(return_value=cm), cookie_jar=[types.SimpleNamespace(value='cookie-secret')])
        client = types.SimpleNamespace(ip='192.0.2.1', username='xcc', password='password-secret', session=session)
        with self.assertLogs(self.ns["__name__"], level="ERROR") as logs:
            with self.assertRaisesRegex(ValueError, 'stopped before page discovery'):
                await self.ns["probe_status"](client)
        session.get.assert_called_once_with(
            'http://192.0.2.1/STATUS.XML', allow_redirects=False, timeout=self.timeout.return_value
        )
        output = ' '.join(logs.output)
        self.assertIn('Access denied', output)
        self.assertIn('status=200', output)
        self.assertIn('content_type=text/html', output)
        self.assertNotIn('cookie-secret', output)
        self.assertNotIn('password-secret', output)


    async def test_login_redirect_reauthenticates_once_and_checks_status_again(self):
        for final_status, final_body in [
            (200, b'<PAGE><INPUT P="X" VALUE="1"/></PAGE>'),
            (302, b''),
        ]:
            with self.subTest(final_status=final_status):
                requests = []

                def response(status, raw):
                    return types.SimpleNamespace(
                        status=status, charset="utf-8", url="http://192.0.2.1/STATUS.XML",
                        headers={"Location": "/LOGIN.HTM"} if status == 302 else {},
                        read=AsyncMock(return_value=raw),
                    )

                cm = Mock()
                cm.__aenter__ = AsyncMock(side_effect=[
                    response(302, b""), response(final_status, final_body)
                ])
                cm.__aexit__ = AsyncMock(return_value=False)

                def get(url, **kwargs):
                    requests.append("status")
                    return cm

                async def authenticate():
                    requests.append("authenticate")

                client = types.SimpleNamespace(
                    ip="192.0.2.1", username="xcc", password="secret",
                    session=types.SimpleNamespace(get=get, cookie_jar=[]),
                    _authenticate=AsyncMock(side_effect=authenticate),
                )
                client.probe_status = types.MethodType(self.ns["probe_status"], client)
                with self.assertLogs(self.ns["__name__"], level="WARNING"):
                    if final_status == 302:
                        with self.assertRaises(self.ns["StatusSessionRejected"]):
                            await self.ns["ensure_status_session"](client)
                    else:
                        await self.ns["ensure_status_session"](client)
                self.assertEqual(requests, ["status", "authenticate", "status"])

    async def test_invalid_data_without_auth_challenge_does_not_authenticate(self):
        client = types.SimpleNamespace(
            ip="192.0.2.1", _authenticate=AsyncMock(),
            probe_status=AsyncMock(side_effect=ValueError("Invalid XML")),
        )
        with self.assertRaisesRegex(ValueError, "Invalid XML"):
            await self.ns["ensure_status_session"](client)
        client._authenticate.assert_not_awaited()


class TestCoordinatorGuard(unittest.IsolatedAsyncioTestCase):
    async def test_bad_probe_prevents_all_other_xml_requests(self):
        tree = ast.parse((XCC / 'coordinator.py').read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
        method = next(n for n in cls.body if isinstance(n, ast.AsyncFunctionDef)
                      and n.name == '_async_update_data_locked')
        package = types.ModuleType('_xcc_guard_test')
        package.__path__ = []
        client_module = types.ModuleType(package.__name__ + '.xcc_client')
        client_module.XCCClient = Mock()
        client_module.parse_xml_entities = Mock()
        sys.modules[package.__name__] = package
        sys.modules[client_module.__name__] = client_module
        self.addCleanup(sys.modules.pop, package.__name__, None)
        self.addCleanup(sys.modules.pop, client_module.__name__, None)
        logger = logging.getLogger(package.__name__)
        ns = {'__package__': package.__name__, 'asyncio': asyncio, 'DEFAULT_TIMEOUT': 1,
              '_LOGGER': logger, 'UpdateFailed': RuntimeError, 'ConfigEntryAuthFailed': RuntimeError}
        future = ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0)
        module = ast.fix_missing_locations(ast.Module(body=[future, method], type_ignores=[]))
        exec(compile(module, 'coordinator.py', 'exec'), ns)
        client = types.SimpleNamespace(
            ensure_status_session=AsyncMock(side_effect=ValueError('Invalid STATUS.XML')),
            fetch_pages=AsyncMock(), fetch_page=AsyncMock(),
        )
        coordinator = types.SimpleNamespace(
            _client=client, ip_address='192.0.2.1', _note_gather_result=Mock(),
            _discover_pages=AsyncMock(), _load_descriptors=AsyncMock(),
        )
        with self.assertLogs(package.__name__, level='ERROR'):
            with self.assertRaisesRegex(RuntimeError, 'Invalid STATUS.XML'):
                await ns['_async_update_data_locked'](coordinator)
        client.ensure_status_session.assert_awaited_once()
        client.fetch_pages.assert_not_awaited()
        client.fetch_page.assert_not_awaited()
        coordinator._discover_pages.assert_not_awaited()
        coordinator._load_descriptors.assert_not_awaited()
        coordinator._note_gather_result.assert_called_once_with([], poll_failed=True)


if __name__ == '__main__':
    unittest.main()
