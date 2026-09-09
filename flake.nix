{
  description = "Read-only CLI for the public Pathé Nederland programme API";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    {
      nixpkgs,
      flake-utils,
      ...
    }:
    (flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = import nixpkgs { inherit system; };
      in
      {
        packages.default = pkgs.callPackage ./nix/package.nix { };

        devShells.default =
          with pkgs;
          mkShell {
            buildInputs = [
              (python3.withPackages (ps: with ps; [
                httpx
                pytest
                pytest-asyncio
                anyio
              ]))
              ruff
            ];

            shellHook = ''
              # src layout: importable without installing.
              export PYTHONPATH="$PWD/src''${PYTHONPATH:+:$PYTHONPATH}"
            '';
          };
      }
    ))
    // {
      overlays.default = final: _prev: {
        pathe-cli = final.callPackage ./nix/package.nix { };
      };

      homeManagerModules.default = ./nix/hm-module.nix;
    };
}
