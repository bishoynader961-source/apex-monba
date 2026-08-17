# Vendored binaries (populated at packaging time)

This directory holds the third-party Windows executables bundled by the Inno
installer (`setup.iss`). They are **not** committed to the repo.

Required layout after packaging:

```
bin/
  nssm/nssm.exe          # service manager (https://nssm.cc)
  caddy/caddy.exe        # reverse proxy + internal CA (https://caddyserver.com)
  sqlite3/sqlite3.exe    # CLI for on-device DB maintenance (optional)
```

`install.ps1` expects `bin\nssm\nssm.exe` and `bin\caddy\caddy.exe`. Download the
matching Windows/amd64 builds and place them here before running the Inno build.
