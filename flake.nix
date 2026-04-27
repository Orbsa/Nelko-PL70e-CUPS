{
  description = "CUPS driver and reverse-engineering shell for the Nelko PL70e-BT 4x6\" thermal printer";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    let
      perSystem = flake-utils.lib.eachDefaultSystem (system:
        let
          pkgs = import nixpkgs { inherit system; };

          python = pkgs.python3.withPackages (ps: with ps; [
            bleak
            pyserial
            pillow
            packaging
            ipython
          ]);

          nelko-pl70e-cups = pkgs.callPackage ./nix/package.nix { };
        in
        {
          packages = {
            default = nelko-pl70e-cups;
            nelko-pl70e-cups = nelko-pl70e-cups;
          };

          devShells.default = pkgs.mkShell {
            packages = [
              python
              pkgs.bluez
              pkgs.wireshark
              pkgs.tshark
              pkgs.xxd
            ];

            shellHook = ''
              echo "Nelko PL70e-BT dev shell"
              echo
              echo "Recon scripts live in tools/:"
              echo "  python tools/recon_scan.py     # BLE scan"
              echo "  python tools/recon_gatt.py     # GATT enumeration"
              echo "  python tools/dot_print.py 50 75   # quick test print"
              echo "  sudo btmon -w captures/trace.btsnoop  # full BLE trace"
            '';
          };
        });
    in
    perSystem // {
      nixosModules = {
        default = ./nix/module.nix;
        nelko-pl70e = ./nix/module.nix;
      };

      overlays.default = final: prev: {
        nelko-pl70e-cups = final.callPackage ./nix/package.nix { };
      };
    };
}
