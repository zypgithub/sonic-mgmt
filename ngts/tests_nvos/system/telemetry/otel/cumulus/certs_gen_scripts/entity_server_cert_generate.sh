#!/bin/bash

CACertFilePrefix="ca"
CACert="ca.crt"
CACertKey="ca.key"
KeyAlg="RSA"
KeyLen="rsa_keygen_bits:4096"
SignHash="-sha256"
ClientAuthEKU=""

TARGET="target.com"
TARGETCertFilePrefix="target"
TARGETCert="target.crt"
TARGETCertKey="target.key"
TARGETSubjAltName="DNS:localhost,IP:127.0.0.1"
TARGETOtherSubjAltNames=""

PKCS12="no"
PKCS12_PASS=""
PKCS12_CA="no"
unset PKCS12_PASS

usage()
{
    usageString="usage: $0 [-ca-cert-file-pref <prefix>] "
    usageString+="[-target-cn <Target Common Name>] "
    usageString+="[-target-san-dns <SAN-DNS>]* "
    usageString+="[-target-san-ip <SAN-IP>]* "

    echo "$usageString"
    echo "   -ca-cert-file-pref <prefix>,      --ca-cert-file-name-prefix <prefix>      Filename prefix of the CA certificate *.crt and *.key files"
    echo "   -target-cn <CN>,                  --target-common-name <CN>                Common name (CN) of the gNMI target (i.e., agent)"
    echo "   -target-cert-file-pref <prefix>,  --target-cert-file-name-prefix <prefix>  Filename prefix of the client certificate *.crt and *.key files"
    echo "   -target-san-dns <DNS>,            --target-subj-alt-name-dns <DNS>         Additional subject alternate names (DNS) for the target certificate."
    echo "                                                                              There can be zero or more such names specified with the flag multiple times."
    echo "   -target-san-ip <IP>,              --target-subj-alt-name-ip-addr <IP>      Additional subject alternate names (IP address) for the target certificate."
    echo "                                                                              There can be zero or more such names specified with the flag multiple times."
    echo "   -client,                          --eku-client                             In addition to TLS/SSL server authentication, also set the TLS/SSL client"
    echo "                                                                              authentication as one of the extended key usage (EKU) purposes."
    echo "   -ecdsa-p521,                      --ecdsa-p521                             Generates an ECDSA P-521 Certificate."
    echo "                                                                              Default: RSA-4096"
    echo "   -sha512,                          --sha512                                 Uses SHA-512 in the signature algorithm."
    echo "                                                                              Default: SHA-256"
    echo "   -pkcs12,                          --pkcs12                                 Create a PKCS#12 bundle of the generated certificate and private key."
    echo "   -pkcs12-pass <pass>,              --pkcs12-passphrase <pass>               Optional argument to protect the PKCS#12 bundle with a passphrase."
    echo "   -pkcs12-ca,                       --pkcs12-include-ca                      If present, also include the CA certificate in the bundled PKCS#12 file."
    echo "   -h,                               --help                                   Prints this message."
    echo ""
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -ca-cert-file-pref | --ca-cert-file-name-prefix )          shift
                                                                   CACertFilePrefix=$1
                                                                   ;;
        -target-cn | --target-common-name )                        shift
                                                                   TARGET=$1
                                                                   ;;
        -target-cert-file-pref | --target-cert-file-name-prefix )  shift
                                                                   TARGETCertFilePrefix=$1
                                                                   ;;
        -target-san-dns | --target-subj-alt-name-dns )             shift
                                                                   TARGETOtherSubjAltNames+=",DNS:$1"
                                                                   ;;
        -target-san-ip | --target-subj-alt-name-ip-addr )          shift
                                                                   TARGETOtherSubjAltNames+=",IP:$1"
                                                                   ;;
        -client | --eku-client )                                   ClientAuthEKU=", clientAuth"
                                                                   ;;
        -ecdsa-p521 | --ecdsa-p521 )                               KeyAlg="EC"
                                                                   KeyLen="ec_paramgen_curve:secp521r1"
                                                                   ;;
        -sha512 | --sha512 )                                       SignHash="-sha512"
                                                                   ;;
        -pkcs12-pass | --pkcs12-passphrase )                       shift
                                                                   PKCS12_PASS=$1
                                                                   ;;
        -pkcs12 | --pkcs12 )                                       PKCS12="yes"
                                                                   ;;
        -pkcs12-ca | --pkcs12-include-ca )                         PKCS12_CA="yes"
                                                                   ;;
        -h | --help )                                              usage
                                                                   exit
                                                                   ;;
        * )                                                        echo "Unknown argument: $1"
                                                                   usage
                                                                   exit 1
    esac
    shift
done

CACert=$CACertFilePrefix.crt
CACertKey=$CACertFilePrefix.key

TARGETCert=$TARGETCertFilePrefix.crt
TARGETCertKey=$TARGETCertFilePrefix.key
TARGETSubjAltName+=",DNS:$TARGET"
if [ "$TARGETOtherSubjAltNames" != "" ]; then
    TARGETSubjAltName+="$TARGETOtherSubjAltNames"
fi

SUBJ="/C=US/ST=CA/L=Santa Clara/O=NVIDIA Corporation/OU=NBU/CN=$TARGET"
SAN="subjectAltName = $TARGETSubjAltName"
V3_CA_EXT="[v3_ca]\nbasicConstraints = CA:FALSE\nkeyUsage = digitalSignature, keyEncipherment\nextendedKeyUsage = critical, serverAuth$ClientAuthEKU\n$SAN"

echo "---------------------------------------------"
echo "Generating Target Private Key: $TARGETCertKey"
echo "---------------------------------------------"
# Generate Target Private Key
openssl genpkey \
        -algorithm $KeyAlg \
        -pkeyopt $KeyLen \
        -out $TARGETCertKey

echo "----------------------------------------------------------------------------------"
echo "Generating Target CSR '$TARGETCertFilePrefix.csr', using the private key '$TARGETCertKey'"
echo "----------------------------------------------------------------------------------"
# Generate Req
openssl req \
        -key $TARGETCertKey \
        $SignHash \
        -new \
        -out $TARGETCertFilePrefix.csr \
        -subj "$SUBJ"

echo "--------------------------------------------------------------------------------"
echo "Generating the Target Certificate '$TARGETCert', using the CSR '$TARGETCertFilePrefix.csr'"
echo "  ----> '$TARGETCert' signed by CA certificate '$CACert'"
echo "--------------------------------------------------------------------------------"
# Generate x509 with signed CA
openssl x509 \
        -req \
        -in $TARGETCertFilePrefix.csr \
        $SignHash \
        -days 365 \
        -CA $CACert \
        -CAkey $CACertKey \
        -CAcreateserial \
        -out $TARGETCert \
        -extensions v3_ca \
        -extfile <(printf "$V3_CA_EXT")

echo ""
echo " == Validate Target Certificate"
openssl verify -verbose -CAfile $CACert $TARGETCert

rm -f *.csr *.srl
chmod 755 $TARGETCert $TARGETCertKey

create_pkcs12()
{
    PKCS_FILE_NAME="${TARGETCertFilePrefix}.p12"

    echo "--------------------------------------------------------------------------------"
    echo "Generating a PKCS#12 bundle - $PKCS_FILE_NAME"
    echo "--------------------------------------------------------------------------------"

    command="openssl pkcs12 -export -out ${PKCS_FILE_NAME} -inkey ${TARGETCertKey} -in ${TARGETCert}"
    if [ "$PKCS12_CA" = "yes" ]; then
        command+=" -certfile ${CACert}"
    fi

    if [ "$PKCS12_PASS" != "" ]; then
        command+=" -passout pass:${PKCS12_PASS}"
    fi

    eval "$command"
}


if [[ "$PKCS12" = "yes" ]]; then
    create_pkcs12
    chmod 755 *.p12
fi

