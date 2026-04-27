{ stdenv
, lib
, fetchurl
, autoPatchelfHook
, writeShellApplication
, python3
, makeWrapper
, symlinkJoin
, cups
}:

let
  # Vendor .deb fetched at build time so we don't redistribute Nelko's binary
  # in this repo. URL is the official driver download from Nelko's CDN.
  vendorDeb = fetchurl {
    url = "https://cdn.shopify.com/s/files/1/0657/6626/0980/files/NELKO_PL70e-BT_Linux_v3.0.1.407.deb";
    hash = "sha256-IinWigCaA9WVWTeTL6x+AXQyvBGCUbOKu1shjYjabUY=";
  };

  vendor = stdenv.mkDerivation {
    pname = "nelko-pl70e-vendor";
    version = "3.0.1.407";
    src = vendorDeb;

    nativeBuildInputs = [ autoPatchelfHook ];

    # The rastertolabel ELF was linked against a system glibc + libstdc++.
    # autoPatchelfHook will rewrite its rpath against these.
    buildInputs = [
      stdenv.cc.cc.lib  # libstdc++/libgcc_s
      cups              # libcups.so.2
    ];

    unpackPhase = ''
      mkdir source
      cd source
      ${stdenv.cc.bintools.bintools_bin}/bin/ar x $src
      tar -xJf data.tar.xz
    '';

    installPhase = ''
      runHook preInstall

      mkdir -p $out/lib/cups/filter/Nelko/Filter
      install -m755 usr/lib/cups/filter/Nelko/Filter/rastertolabel \
        $out/lib/cups/filter/Nelko/Filter/rastertolabel

      mkdir -p $out/share/cups/model/Nelko
      install -m644 usr/share/cups/model/Nelko/PL70e-BT.ppd \
        $out/share/cups/model/Nelko/PL70e-BT.ppd
      install -m644 usr/share/cups/model/Nelko/PL420.ppd \
        $out/share/cups/model/Nelko/PL420.ppd

      runHook postInstall
    '';

    meta = {
      description = "Vendor CUPS filter and PPDs for the Nelko PL70e-BT";
      platforms = [ "x86_64-linux" ];
    };
  };

  pythonEnv = python3.withPackages (ps: with ps; [ bleak ]);

  backend = stdenv.mkDerivation {
    pname = "nelko-pl70e-backend";
    version = "0.1.0";
    src = ../.;
    dontUnpack = false;

    nativeBuildInputs = [ makeWrapper ];

    installPhase = ''
      runHook preInstall

      # CUPS backends need to be executable by root and named after the URI
      # scheme they handle.
      install -d $out/lib/cups/backend
      install -m755 $src/cups_backend/pl70e_ble.py $out/lib/cups/backend/ble
      sed -i "1s|.*|#!${pythonEnv}/bin/python3|" $out/lib/cups/backend/ble

      # Setup CLI on PATH for nix-profile / NixOS users.
      install -d $out/bin
      install -m755 $src/bin/nelko-setup $out/bin/nelko-setup
      sed -i "1s|.*|#!${pythonEnv}/bin/python3|" $out/bin/nelko-setup

      runHook postInstall
    '';

    meta = {
      description = "BLE CUPS backend and setup CLI for Nelko PL70e-BT";
      platforms = [ "x86_64-linux" ];
    };
  };

in
symlinkJoin {
  name = "nelko-pl70e-cups-0.1.0";
  paths = [ vendor backend ];
  passthru = { inherit vendor backend pythonEnv; };
  meta = {
    description = "Nelko PL70e-BT CUPS driver bundle (PPD + filter + BLE backend + setup CLI)";
    platforms = [ "x86_64-linux" ];
  };
}
