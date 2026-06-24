#!/bin/bash

CA="ca"
CACertFilePrefix="ca"
CACert=ca.crt
CACertKey=ca.key
KeyAlg="RSA"
KeyLen="rsa_keygen_bits:4096"
SignHash="-sha256"

PKCS12="no"
PKCS12_PASS=""
unset PKCS12_PASS

usage()
{
    echo "usage: $0 [-ca <CA Common Name>] [-ca-cert-file-pref <prefix>]"
    echo ""
    echo "   -ca <CN>,                  --ca-common-name <CN>              Common name (CN) of the fake Certificate Authority (CA)"
    echo "                                                                 Default: 'ca'"
    echo "   -ca-cert-file-pref <name>, --ca-cert-file-name-prefix <name>  Generated CA Certificate *.crt and *.key file name prefix"
    echo "                                                                 Default: 'ca.crt' and 'ca.key'"
    echo "   -ecdsa-p521,               --ecdsa-p521                       Generates an ECDSA P-521 Certificate"
    echo "                                                                 Default: RSA-4096"
    echo "   -sha512,                   --sha512                           Uses SHA-512 in the signature algorithm."
    echo "                                                                 Default: SHA-256"
    echo "   -pkcs12,                   --pkcs12                           Create a PKCS#12 bundle of the generated certificate and private key."
    echo "   -pkcs12-pass <pass>,       --pkcs12-passphrase <pass>         Optional argument to protect the PKCS#12 bundle with a passphrase."
    echo "   -h,                        --help                             Prints this message"
}

while [ "$1" != "" ]; do
    case $1 in
        -ca | --ca-common-name )                           shift
                                                           CA=$1
                                                           ;;
        -ca-cert-file-pref | --ca-cert-file-name-prefix )  shift
                                                           CACertFilePrefix=$1
                                                           ;;
        -ecdsa-p521 | --ecdsa-p521 )                       KeyAlg="EC"
                                                           KeyLen="ec_paramgen_curve:secp521r1"
                                                           ;;
        -sha512 | --sha512 )                               SignHash="-sha512"
                                                           ;;
        -pkcs12-pass | --pkcs12-passphrase )               shift
                                                           PKCS12_PASS=$1
                                                           ;;
        -pkcs12 | --pkcs12 )                               PKCS12="yes"
                                                           ;;
        -h | --help )                                      usage
                                                           exit
                                                           ;;
        * )                                                usage
                                                           exit 1
    esac
    shift
done


CACert=$CACertFilePrefix.crt
CACertKey=$CACertFilePrefix.key


SUBJ="/C=US/ST=CA/L=Santa Clara/O=NVIDIA Corporation/OU=NBU/CN=$CA"
V3_CA_EXT="[v3_ca]\nbasicConstraints = CA:TRUE"

echo "---------------------------------------"
echo "Generating CA Private Key: $CACertKey"
echo "---------------------------------------"

# Generate CA Private Key
openssl genpkey \
        -algorithm $KeyAlg \
        -pkeyopt $KeyLen \
        -out $CACertKey

echo "----------------------------------------------------------------------------------"
echo "Generating CA CSR '$CACertFilePrefix.csr', using the private key '$CACertKey'"
echo "----------------------------------------------------------------------------------"

# Generate Req
openssl req \
        -key $CACertKey \
        -new \
        $SignHash \
        -out $CACertFilePrefix.csr \
        -subj "$SUBJ"

echo "--------------------------------------------------------------------------------"
echo "Generating the CA Certificate '$CACert', using the CSR '$CACertFilePrefix.csr'"
echo "--------------------------------------------------------------------------------"
# Generate self signed x509
openssl x509 \
        -signkey $CACertKey \
        -in $CACertFilePrefix.csr \
        $SignHash \
        -req \
        -days 365 \
        -out $CACert \
        -extensions v3_ca \
        -extfile <(printf "$V3_CA_EXT")

chmod 755 *ca.*
rm -f *.csr *.srl

create_pkcs12()
{
    PKCS_FILE_NAME="${CACertFilePrefix}.p12"

    echo "--------------------------------------------------------------------------------"
    echo "Generating a PKCS#12 bundle - $PKCS_FILE_NAME"
    echo "--------------------------------------------------------------------------------"

    command="openssl pkcs12 -export -out ${PKCS_FILE_NAME} -inkey ${CACertKey} -in ${CACert}"

    if [ "$PKCS12_PASS" != "" ]; then
        command+=" -passout pass:${PKCS12_PASS}"
    fi

    eval "$command"
}


if [[ "$PKCS12" = "yes" ]]; then
    create_pkcs12
fi