# Install necessary packages
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y slapd time ldap-utils openssl tcpdump openssl gnutls-bin ssl-cert openssh-client vim less net-tools

# Start slapd
service slapd start &&
slap_passwd_hash=$(slappasswd -h {SSHA} -s {BIND_PASSWORD})

# Configure db
############################
# STEP: general db entries #
############################
echo "dn: olcDatabase={1}mdb,cn=config
changetype: modify
replace: olcSuffix
olcSuffix: {BASE_DN}

dn: olcDatabase={1}mdb,cn=config
changetype: modify
replace: olcRootDN
olcRootDN: cn={BIND_USERNAME},{BASE_DN}

dn: olcDatabase={1}mdb,cn=config
changetype: modify
replace: olcRootPW
olcRootPW: $slap_passwd_hash" > db.ldif &&
ldapmodify -Y EXTERNAL  -H ldapi:/// -f db.ldif


############################
# STEP: root entries #
############################
echo "dn: {BASE_DN}
dc: itzgeek
objectClass: top
objectClass: domain

dn: cn={BIND_USERNAME},{BASE_DN}
objectClass: organizationalRole
cn: {BIND_USERNAME}
description: LDAP Manager

dn: ou=Users,{BASE_DN}
objectClass: organizationalUnit
ou: Users

dn: ou=Groups,{BASE_DN}
objectClass: organizationalUnit
ou: Groups" > base.ldif &&
ldapadd -x -w {BIND_PASSWORD} -D "cn={BIND_USERNAME},{BASE_DN}" -f base.ldif


############################
# STEP: users #
############################
# encode base64: echo -n "SOMETHING" | base64
# decode base64: echo -n "SOMETHING" | base64 -d
############################
echo "dn: uid={USERNAME},ou=Users,{BASE_DN}
objectClass: inetOrgPerson
objectClass: posixAccount
objectClass: shadowAccount
uid: {USERNAME}
cn: {USERNAME}
uidNumber: 1111
gidNumber: 1000
userPassword:: {PASSWORD}
homeDirectory: /home/{USERNAME}
loginShell: /bin/bash
sn: {USERNAME}
givenName: {USERNAME}
displayName: Mumbo Jumbo Dumbo" > users.ldif &&
ldapadd -x -w {BIND_PASSWORD} -D "cn={BIND_USERNAME},{BASE_DN}" -f users.ldif


############################
# STEP: groups #
############################
echo "dn: cn=admin,ou=Groups,{BASE_DN}
objectClass: posixGroup
cn: admin
gidNumber: 1000
memberUid: {USERNAME}

dn: cn=sudo,ou=Groups,{BASE_DN}
objectClass: posixGroup
cn: sudo
gidNumber: 27
memberUid: {USERNAME}

dn: cn=docker,ou=Groups,{BASE_DN}
objectClass: posixGroup
cn: docker
gidNumber: 999
memberUid: {USERNAME}

dn: cn=redis,ou=Groups,{BASE_DN}
objectClass: posixGroup
cn: redis
gidNumber: 1001
memberUid: {USERNAME}

dn: cn=ldapgrp,ou=Groups,{BASE_DN}
objectClass: posixGroup
cn: ldapgrp
gidNumber: 9999
memberUid: {USERNAME}" > ldap-group.ldif
ldapadd -x -w {BIND_PASSWORD} -D "cn={BIND_USERNAME},{BASE_DN}" -f ldap-group.ldif


# TLS support :
# /C=GB/ST=London/L=London/O=Ldap test/OU=Ldap test/
# From https://kifarunix.com/setup-openldap-server-with-ssl-tls-on-debian-10/
DEBIAN_FRONTEND=noninteractive apt-get install -y openssl

mkdir -p /etc/ssl/openldap/{private,certs,newcerts}
sed -i  "s/dir.*demoCA.*Where everything is kept/dir\t\t= \/etc\/ssl\/openldap/" /usr/lib/ssl/openssl.cnf
echo "1001" > /etc/ssl/openldap/serial
touch /etc/ssl/openldap/index.txt
openssl genrsa -aes256 -passout pass:1234 -out /etc/ssl/openldap/private/cakey.pem 2048
openssl rsa  --passin pass:1234  -in /etc/ssl/openldap/private/cakey.pem -out /etc/ssl/openldap/private/cakey.pem
openssl req -new -x509 -subj "/C=GB/ST=London/L=London/O=Ldap test/OU=Users/CN=ldap.itzgeek.local/" -days 3650 -key /etc/ssl/openldap/private/cakey.pem -out /etc/ssl/openldap/certs/cacert.pem

openssl genrsa -aes256 -passout pass:1234 -out /etc/ssl/openldap/private/ldapserver-key.key 2048
openssl rsa --passin pass:1234 -in /etc/ssl/openldap/private/ldapserver-key.key -out /etc/ssl/openldap/private/ldapserver-key.key

openssl req -new -subj "/C=GB/ST=London/L=London/O=Ldap test/OU=Users/CN=ldap.itzgeek.local/" -key /etc/ssl/openldap/private/ldapserver-key.key -out /etc/ssl/openldap/certs/ldapserver-cert.csr
openssl ca -batch  -keyfile /etc/ssl/openldap/private/cakey.pem -cert /etc/ssl/openldap/certs/cacert.pem -in /etc/ssl/openldap/certs/ldapserver-cert.csr -out /etc/ssl/openldap/certs/ldapserver-cert.crt
openssl verify -CAfile /etc/ssl/openldap/certs/cacert.pem /etc/ssl/openldap/certs/ldapserver-cert.crt
chown -R openldap: /etc/ssl/openldap/
echo "dn: cn=config
changetype: modify
add: olcTLSCACertificateFile
olcTLSCACertificateFile: /etc/ssl/openldap/certs/cacert.pem
-
replace: olcTLSCertificateFile
olcTLSCertificateFile: /etc/ssl/openldap/certs/ldapserver-cert.crt
-
replace: olcTLSCertificateKeyFile
olcTLSCertificateKeyFile: /etc/ssl/openldap/private/ldapserver-key.key" > ldap-tls.ldif
ldapmodify -Y EXTERNAL -H ldapi:/// -f ldap-tls.ldif

sed -i "s/SLAPD_SERVICES=.*/SLAPD_SERVICES=\"ldap:\/\/\/ ldapi:\/\/\/ ldaps:\/\/\/\"/g" /etc/default/slapd
sleep 1
slapcat -b "cn=config" | grep -E "olcTLS"
sleep 1
service slapd force-reload

sleep 5

service slapd status
echo "Done setup script!"

