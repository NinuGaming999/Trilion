---
name: take-notes
description: Save notes, ideas or research to a text file in Documents.
---
1. Folder: Documents\Trilion Notes. Create it with run_shell: powershell -c "New-Item -ItemType Directory -Force -Path \"$HOME\Documents\Trilion Notes\"".
2. File name: today's date as YYYY-MM-DD.txt. If it exists, read_file it first and write it back with the new note added at the end.
3. Use write_file with the full path. Tell the user the file name when done.
