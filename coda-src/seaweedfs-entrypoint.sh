#!/bin/sh
set -eu
umask 077

server_dir=/run/seaweedfs-server-tls
trust_dir=/run/seaweedfs-ca
mkdir -p "$server_dir" "$trust_dir"

if [ ! -s "$server_dir/ca.key" ] || [ ! -s "$server_dir/ca.crt" ]; then
    openssl req -x509 -newkey rsa:3072 -sha256 -nodes -days 3650 \
        -keyout "$server_dir/ca.key" \
        -out "$server_dir/ca.crt" \
        -subj '/CN=CODDAA internal SeaweedFS CA' \
        -addext 'basicConstraints=critical,CA:TRUE' \
        -addext 'keyUsage=critical,keyCertSign,cRLSign'
fi

certificate_dir=$(mktemp -d "$server_dir/.certificate.XXXXXX")
trap 'rm -rf "$certificate_dir"' EXIT HUP INT TERM

openssl req -new -newkey rsa:2048 -sha256 -nodes \
    -keyout "$certificate_dir/server.key" \
    -out "$certificate_dir/server.csr" \
    -subj '/CN=seaweedfs'

cat > "$certificate_dir/server.ext" <<'EOF'
subjectAltName=DNS:seaweedfs
extendedKeyUsage=serverAuth
keyUsage=digitalSignature,keyEncipherment
basicConstraints=CA:FALSE
EOF

openssl x509 -req -sha256 -days 30 \
    -in "$certificate_dir/server.csr" \
    -CA "$server_dir/ca.crt" \
    -CAkey "$server_dir/ca.key" \
    -CAcreateserial \
    -out "$certificate_dir/server.crt" \
    -extfile "$certificate_dir/server.ext"

# weed corre como usuario sin privilegios: sólo la hoja es legible por él; ca.key queda root-only.
chown 1000:1000 "$certificate_dir/server.key" "$certificate_dir/server.crt"
chmod 0400 "$certificate_dir/server.key"
chmod 0444 "$certificate_dir/server.crt"
chmod 0711 "$server_dir"

mv "$certificate_dir/server.key" "$server_dir/server.key.new"
mv "$certificate_dir/server.crt" "$server_dir/server.crt.new"
mv "$server_dir/server.key.new" "$server_dir/server.key"
mv "$server_dir/server.crt.new" "$server_dir/server.crt"
cp "$server_dir/ca.crt" "$trust_dir/ca.crt.new"
chmod 0444 "$trust_dir/ca.crt.new"
mv "$trust_dir/ca.crt.new" "$trust_dir/ca.crt"

exec /entrypoint.sh "$@"
