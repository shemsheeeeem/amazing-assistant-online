Amazing Assistants Online
==========================

Double-click run.bat. The site opens at http://127.0.0.1:5070/

The first launch installs Python packages. That takes about a minute.
Keep the black window open while you use the site.

Accounts, profiles, jobs, and applications are saved in the data folder
next to this file. They stay on this computer.

To start fresh, close the window, delete the data folder, and run again.

The live site uses this start command:

gunicorn --bind 0.0.0.0:$PORT app:app
