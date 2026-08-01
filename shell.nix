{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {

  packages = [
    (pkgs.python3.withPackages (ps: [
      ps.pip
      ps.flask
      ps.flask-socketio
      ps.python-socketio
      ps.simple-websocket
      ps.gunicorn
      # Dev tools, so `pytest` and `ruff` work in the shell without a venv.
      ps.pytest
      ps.ruff
    ]))
  ];

  shellHook = ''
    export CATAN_CONFIG=''${CATAN_CONFIG:-development}
    echo "CatanPro dev shell — run: python server/app.py"
  '';

}
