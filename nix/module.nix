{ config, lib, pkgs, ... }:

let
  cfg = config.services.nelko-pl70e;
  nelkoPkg = pkgs.callPackage ./package.nix { };
in
{
  options.services.nelko-pl70e = {
    enable = lib.mkEnableOption "CUPS support for the Nelko PL70e-BT thermal printer over BLE";

    macAddress = lib.mkOption {
      type = lib.types.str;
      example = "DC:0D:30:5A:A7:F5";
      description = ''
        The printer's BLE (LE) MAC address. This is usually different from the
        Bluetooth Classic address shown by iOS/Android — find it via a BLE scan
        (e.g. `bluetoothctl scan le`) or with the project's `recon_scan.py`.
      '';
    };

    name = lib.mkOption {
      type = lib.types.str;
      default = "PL70e";
      description = "CUPS queue name to register.";
    };

    pageSize = lib.mkOption {
      type = lib.types.str;
      default = "w288h432";
      description = ''
        PPD PageSize option. Default `w288h432` is 4"x6" (101.6x152.4 mm).
        See drivers/extracted/usr/share/cups/model/Nelko/PL70e-BT.ppd for the
        full list of supported page sizes.
      '';
    };

    channel = lib.mkOption {
      type = lib.types.enum [ "fff2" "fec7" "issc" ];
      default = "fff2";
      description = "GATT write characteristic to use for the print stream.";
    };

    setAsDefault = lib.mkOption {
      type = lib.types.bool;
      default = false;
      description = "Make this printer the system default.";
    };
  };

  config = lib.mkIf cfg.enable {
    # CUPS itself + our driver bundle.
    services.printing = {
      enable = true;
      drivers = [ nelkoPkg ];
      # The backend connects on demand; keep the daemon ready.
      startWhenNeeded = lib.mkDefault false;
    };

    # Ensure Bluetooth stack is present and powered (the BLE backend needs it).
    hardware.bluetooth.enable = true;
    hardware.bluetooth.powerOnBoot = true;

    # `powerOnBoot` only takes effect when bluez has no persisted state for the
    # adapter. If the user (or another tool) has ever run `power off`, bluez
    # writes `Powered=false` to /var/lib/bluetooth/<addr>/settings and respects
    # it across reboots — leaving the BLE backend with no adapter to bind to.
    # Force the adapter on after bluetoothd is up.
    systemd.services.nelko-bluetooth-power-on = {
      description = "Power on Bluetooth adapter for Nelko PL70e BLE backend";
      after = [ "bluetooth.service" ];
      requires = [ "bluetooth.service" ];
      wantedBy = [ "multi-user.target" ];
      serviceConfig = {
        Type = "oneshot";
        ExecStart = "${pkgs.bluez}/bin/bluetoothctl power on";
      };
    };

    # The cups-browsed/cupsd workers run as the `lp` user. They need to talk to
    # bluetoothd over D-Bus. polkit normally restricts org.bluez.* to active
    # sessions; this rule whitelists the `lp` user explicitly.
    security.polkit.extraConfig = ''
      polkit.addRule(function(action, subject) {
        if (action.id.indexOf("org.bluez.") === 0 &&
            subject.user === "lp") {
          return polkit.Result.YES;
        }
      });
    '';

    # Declaratively register the printer queue.
    # MAC is dashed in the URI: CUPS's URI parser treats colons in the host
    # as port separators, so a raw MAC fails validation in lpadmin.
    hardware.printers.ensurePrinters = [
      {
        name = cfg.name;
        location = "Local BLE";
        deviceUri = "ble://${lib.replaceStrings [":"] ["-"] cfg.macAddress}?channel=${cfg.channel}";
        model = "Nelko/PL70e-BT.ppd";
        ppdOptions = {
          PageSize = cfg.pageSize;
        };
      }
    ];

    hardware.printers.ensureDefaultPrinter =
      lib.mkIf cfg.setAsDefault cfg.name;
  };
}
