#!/bin/bash
#$BUG_HANDLER_VENV : need to set the venv of it. such as "/ngts_venv/bin/"

set -ex

echo "Back up the tests/common/__init__.py"
cp ../../../__init__.py ../../../__init__.py.1
echo "Back up the tests/common/plugins/loganalyzer/__init__.py"
cp ../__init__.py ../__init__.py.1

echo "Clean up the content in tests/common/__init__.py file to avoid the loading other unneeded module"
echo "" > ../../../__init__.py
echo "Clean up the content in tests/common/plugins/loganalyzer/__init__.py file to avoid the loading other unneeded module"
echo "" > ../__init__.py

$BUG_HANDLER_VENV/pip install -r requirements.txt
$BUG_HANDLER_VENV/pyinstaller bug_handler.spec --noconfirm --clean

#cp the ./dist/bug_handler/bug_handler and ./dist/bug_handler/_internal to /auto/sw_system_release/sonic/bughandler
echo "Recover the tests/common/__init__.py"
mv ../../../__init__.py.1 ../../../__init__.py
echo "Recover the tests/common/plugins/loganalyzer/__init__.py"
mv ../__init__.py.1 ../__init__.py

echo "Copy the bughandler standalone tool to /auto/sw_system_release/sonic/bughandler"
cp ./dist/bug_handler/bug_handler /auto/sw_system_release/sonic/bughandler
cp -r ./dist/bug_handler/_internal /auto/sw_system_release/sonic/bughandler