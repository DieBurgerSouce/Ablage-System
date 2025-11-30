#!/bin/sh

# Replace env vars in JavaScript files
echo "Replacing env vars in JS files"
for file in /usr/share/nginx/html/assets/*.js;
do
  if [ ! -f $file.tmpl.js ]; then
    cp $file $file.tmpl.js
  fi
  envsubst '$VITE_API_BASE_URL $VITE_WS_BASE_URL' < $file.tmpl.js > $file
done

exec "$@"
