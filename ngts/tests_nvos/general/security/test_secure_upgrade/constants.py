
TEST_DIR = '/auto/sw_system_project/NVOS_INFRA/security/verification/secure_upgrade'
NON_SECURED_IMG_FILE = f'{TEST_DIR}/nvos_not_signed.bin'

PROD_IMG_FILE = f'{TEST_DIR}/prod-image.bin'  # TODO: complete when there's build with prod
DEV_IMG_FILE = f'{TEST_DIR}/dev-image.bin'   # TODO: complete when there's build with prod

BEGIN_CMS = '-----BEGIN CMS-----'

LAST_LINE_INJECTED_TEXT_IMG = 'image-with-text-injected-to-last-line'
BAD_SIGNATURE_IMG = 'bad-signature-image'
BAD_PAYLOAD_IMG = 'bad-payload-image'
PROD_IMG = 'prod-image'
DEV_IMG = 'dev-image'
