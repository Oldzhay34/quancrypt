select
    {{ sk(['code']) }} as usage_context_sk,
    code as usage_context,
    description,
    code in ('TLS_KEY_EXCHANGE', 'KEY_AGREEMENT', 'ENCRYPTION', 'KEY_WRAP') as is_key_establishment_or_encryption
from {{ source('prep', 'usage_context') }}
