{
  lib,
  python3Packages,
}:

python3Packages.buildPythonApplication {
  pname = "pathe-cli";
  version = "0.1.0";
  pyproject = true;

  src = lib.cleanSource ../.;

  build-system = [ python3Packages.hatchling ];

  dependencies = [ python3Packages.httpx ];

  nativeCheckInputs = with python3Packages; [
    pytestCheckHook
    pytest-asyncio
    # anyio ships the pytest plugin the async tests mark themselves with; it
    # arrives via httpx anyway, but naming it here keeps the check phase honest
    # if that ever stops being true.
    anyio
  ];

  # The suite is entirely offline -- every test drives a fake client backed by
  # fixtures recorded from the live API -- so it runs unchanged in the sandbox.
  pythonImportsCheck = [ "pathe" ];

  meta = {
    description = "Read-only CLI for the public Pathé Nederland programme API";
    longDescription = ''
      Queries www.pathe.nl's public JSON API for cinema programmes, showtimes,
      and the Arthouse / Pride Night / Classics strands. No API key and no
      login: every endpoint it touches is an unauthenticated GET, and it cannot
      book a seat.
    '';
    license = lib.licenses.mit;
    mainProgram = "pathe";
    platforms = lib.platforms.all;
  };
}
