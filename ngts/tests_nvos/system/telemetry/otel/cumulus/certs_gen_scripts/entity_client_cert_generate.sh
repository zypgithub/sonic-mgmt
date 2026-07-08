#!/bin/bash

CACertFilePrefix="ca"
CACert="ca.crt"
CACertKey="ca.key"
KeyAlg="RSA"
KeyLen="rsa_keygen_bits:4096"
SignHash="-sha256"

CLIENT="client.com"
CLIENTCertFilePrefix="client"
CLIENTCert="client.crt"
CLIENTCertKey="client.key"
CLIENTSubjAltName="DNS:localhost,IP:127.0.0.1"
ClientOtherSubjAltNames=""

PKCS12="no"
PKCS12_PASS=""
PKCS12_CA="no"
unset PKCS12_PASS

usage()
{
    usageString="usage: $0 [-ca-cert-file-pref <prefix>] "
    usageString+="[-client-cn <Client Common Name>] "
    usageString+="[-client-san-dns <SAN>]* "
    usageString+="[-client-san-ip <SAN-IP>]*"

    echo "$usageString"
    echo "   -ca-cert-file-pref <prefix>,     --ca-cert-file-name-prefix <prefix>      Filename prefix of the CA certificate *.crt and *.key files"
    echo "   -client-cn <CN>,                 --client-common-name <CN>                Common name (CN) of the gNMI client"
    echo "   -client-cert-file-pref <prefix>, --client-cert-file-name-prefix <prefix>  Filename prefix of the target certificate *.crt and *.key files"
    echo "   -client-san-dns <DNS>,           --client-subj-alt-name-dns <DNS>         Additional subject alternate names (DNS) for the client certificate."
    echo "                                                                             There can be zero or more such names specified with the flag multiple times."
    echo "   -client-san-ip <IP>,             --client-subj-alt-name-ip-addr <IP>      Additional subject alternate names (IP address) for the client certificate."
    echo "                                                                             There can be zero or more such names specified with the flag multiple times."
    echo "   -ecdsa-p521,                     --ecdsa-p521                             Generates an ECDSA P-521 Certificate."
    echo "                                                                             Default: RSA-4096"
    echo "   -sha512,                         --sha512                                 Uses SHA-512 in the signature algorithm."
    echo "                                                                             Default: SHA-256"
    echo "   -pkcs12,                         --pkcs12                                 Create a PKCS#12 bundle of the generated certificate and private key."
    echo "   -pkcs12-pass <pass>,             --pkcs12-passphrase <pass>               Optional argument to protect the PKCS#12 bundle with a passphrase."
    echo "   -pkcs12-ca,                      --pkcs12-include-ca                      If present, also include the CA certificate in the bundled PKCS#12 file."

    echo "   -h,                              --help                                   Prints this message"
    echo ""
}

while [[ $# -gt 0 ]]; do
    case $1 in
        -ca-cert-file-pref | --ca-cert-file-name-prefix )          shift
                                                                   CACertFilePrefix=$1
                                                                   ;;
        -client-cn | --client-common-name )                        shift
                                                                   CLIENT=$1
                                                                   ;;
        -client-cert-file-pref | --client-cert-file-name-prefix )  shift
                                                                   CLIENTCertFilePrefix=$1
                                                                   ;;
        -client-san-dns | --client-subj-alt-name-dns )             shift
                                                                   CLIENTOtherSubjAltNames+=",DNS:$1"
                                                                   ;;
        -client-san-ip | --client-subj-alt-name-ip-addr )          shift
                                                                   CLIENTOtherSubjAltNames+=",IP:$1"
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
        * )                                                        usage
                                                                   exit 1
    esac
    shift
done

CACert=$CACertFilePrefix.crt
CACertKey=$CACertFilePrefix.key

CLIENTCert=$CLIENTCertFilePrefix.crt
CLIENTCertKey=$CLIENTCertFilePrefix.key
CLIENTSubjAltName+=",DNS:$CLIENT"
if [ "$CLIENTOtherSubjAltNames" != "" ]; then
    CLIENTSubjAltName+="$CLIENTOtherSubjAltNames"
fi

SUBJ="/C=US/ST=CA/L=San Jose/O=Infinera Corporation/OU=Test/CN=$CLIENT"
SAN="subjectAltName = $CLIENTSubjAltName"
V3_CA_EXT="[v3_ca]\nbasicConstraints = CA:FALSE\nkeyUsage = digitalSignature, keyEncipherment\nextendedKeyUsage = critical, clientAuth\n$SAN"

echo "---------------------------------------------"
echo "Generating Client Private Key: $CLIENTCertKey"
echo "---------------------------------------------"
# Generate Client Private Key
openssl genpkey \
        -algorithm $KeyAlg \
        -pkeyopt $KeyLen \
        -out $CLIENTCertKey

echo "----------------------------------------------------------------------------------"
echo "Generating Client CSR '$CLIENTCertFilePrefix.csr', using the private key '$CLIENTCertKey'"
echo "----------------------------------------------------------------------------------"
# Generate Req
openssl req \
        -key $CLIENTCertKey \
        $SignHash \
        -new \
        -out $CLIENTCertFilePrefix.csr \
        -subj "$SUBJ"

echo "--------------------------------------------------------------------------------"
echo "Generating the Client Certificate '$CLIENTCert', using the CSR '$CLIENTCertFilePrefix.csr'"
echo "  ----> '$CLIENTCert' signed by CA certificate '$CACert'"
echo "--------------------------------------------------------------------------------"
# Generate x509 with signed CA
openssl x509 \
        -req \
        -in $CLIENTCertFilePrefix.csr \
        $SignHash \
        -days 365 \
        -CA $CACert \
        -CAkey $CACertKey \
        -CAcreateserial \
        -out $CLIENTCert \
        -extensions v3_ca \
        -extfile <(printf "$V3_CA_EXT")

echo ""
echo " == Validate Client Certificate"
openssl verify -verbose -CAfile $CACert $CLIENTCert

rm -f *.csr *.srl
chmod 755 $CLIENTCert $CLIENTCertKey

create_pkcs12()
{
    PKCS_FILE_NAME="${CLIENTCertFilePrefix}.p12"

    echo "--------------------------------------------------------------------------------"
    echo "Generating a PKCS#12 bundle - $PKCS_FILE_NAME"
    echo "--------------------------------------------------------------------------------"

    command="openssl pkcs12 -export -out ${PKCS_FILE_NAME} -inkey ${CLIENTCertKey} -in ${CLIENTCert}"
    if [ "$PKCS12_CA" = "yes" ]; then
        command+=" -certfile ${CACert}"
    fi

    if [ "$PKCS12_PASS" != "" ]; then
        command+=" -passout pass:$PKCS12_PASS"
    fi

    eval "$command"
}


if [[ "$PKCS12" = "yes" ]]; then
    create_pkcs12
    chmod 755 *.p12
fi