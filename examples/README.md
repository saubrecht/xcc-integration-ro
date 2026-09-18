# Home Assistant examples

## Deco household Wi-Fi notifications

`deco_household_wifi_notifications.yaml` is an automation blueprint for
notifying when household mobile devices join or leave the home Wi-Fi exposed by
the Deco integration.

1. In Home Assistant, open **Settings → Automations & scenes → Blueprints** and
   import the YAML file from this repository.
2. Create an automation from **Deco household Wi-Fi presence notifications**.
3. Select the Deco `device_tracker` entities for the household phones and
   tablets, select one or more **notify** entities as notification targets, and
   retain the five-minute delay (or adjust it to suit the mesh).

For example, select `notify.alices_phone` and `notify.bobs_phone`. These are
entities (not the legacy `notify.mobile_app_*` action names) and can be found in
**Settings → Devices & services → Entities**.

Optionally set **Device aliases** to a YAML mapping such as the following. The
alias is used in alerts; devices omitted from the mapping retain their Deco name.

```yaml
device_tracker.deco_alices_iphone: Alice
device_tracker.deco_bobs_pixel: Bob
```

Both joining and leaving must remain stable for the confirmation interval. That
prevents duplicate “left” and “connected” alerts when a phone briefly changes
between Deco mesh nodes.

## Confirmed Wi-Fi presence

`deco_confirmed_wifi_presence.yaml` is the more robust option for a Deco mesh.
Create one `input_boolean` helper for each household device, then create one
automation from this blueprint for that device and helper. Set the helper to
match the device's current presence before enabling the automation.

The helper changes only after a confirmed arrival or departure. A short mesh
handoff therefore leaves it unchanged, and the later return to `home` does not
generate a false arrival notification.
