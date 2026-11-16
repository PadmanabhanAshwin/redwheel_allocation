#!/bin/zsh
# Build the polished deck: polish/object.html, p1..pN.png, and ../redwheel_deck_polish.pdf. Leaves object/ and LATEST untouched.
set -e
cd "${0:A:h}"
CH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
python3 build.py .
"$CH" --headless=new --disable-gpu --no-pdf-header-footer --print-to-pdf="$PWD/../redwheel_deck_polish.pdf" "file://$PWD/object.html" 2>/dev/null
for f in p*.html; do "$CH" --headless=new --disable-gpu --hide-scrollbars --window-size=1920,1080 --screenshot="$PWD/${f%.html}.png" "file://$PWD/$f" 2>/dev/null; done
echo built
