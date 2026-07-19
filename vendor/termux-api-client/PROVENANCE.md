# Project-local Termux:API client

- Official source: `https://github.com/termux/termux-api-package`
- Source archive SHA-256: `dbc6fdede1650c71c73289dbfe9dba404b65f4a5e8981d00e422c1556f55fe10`
- Official Termux repository package: `termux-api 0.59.1-1`
- Repository package SHA-256: `2b45c985c49420467b3452fd10d5e570a108d20bb2057a13b4d47f5a147f6186`

The client is compiled into `runtime/` with a project-local prefix. Its shell,
bash, and Android activity-manager entries are read-only symlinks to the
existing Termux executables. No global Termux package is installed or changed.
