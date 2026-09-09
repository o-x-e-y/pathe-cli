{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.programs.pathe;
in
{
  options.programs.pathe = {
    enable = lib.mkEnableOption "the pathe CLI";

    package = lib.mkOption {
      type = lib.types.package;
      default = pkgs.pathe-cli;
      defaultText = lib.literalExpression "pkgs.pathe-cli";
      description = ''
        The package to install. The default needs this flake's
        `overlays.default` in `nixpkgs.overlays`.
      '';
    };

    favorites = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [ ];
      example = [
        "helmond"
        "tilburg-stappegoor"
      ];
      description = ''
        Cinemas used when no `-c` is given, and what `-f` selects.

        An entry may be a full slug (`pathe-helmond`), the slug without the
        prefix (`helmond`), or any unique substring of one; `pathe cinemas`
        lists them all. Note that not every cinema carries the prefix --
        `koninklijk-theater-tuschinski` does not.

        Left empty, no settings file is written and the CLI keeps its built-in
        default.
      '';
    };
  };

  config = lib.mkIf cfg.enable {
    home.packages = [ cfg.package ];

    xdg.configFile."pathe/settings.json" = lib.mkIf (cfg.favorites != [ ]) {
      text = builtins.toJSON { favorites = cfg.favorites; };
    };
  };
}
