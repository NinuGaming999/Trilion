---
name: organize-folder
description: Tidy a folder (Downloads, Desktop, ...) by sorting files into subfolders safely.
---
1. list_dir the folder. Group files by type (Images, Videos, Documents, Archives, Installers, Other).
2. Tell the user the plan in one or two sentences and wait for a clear yes before moving anything.
3. Move files with run_shell (PowerShell Move-Item). Never delete anything. Never overwrite: skip names that already exist.
4. list_dir again to verify, then report how many files moved.
