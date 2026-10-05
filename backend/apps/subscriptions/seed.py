"""
DUMMY seed values for the plan table — PLACEHOLDERS, NOT REAL PRICING.

The owner replaces every number in Django admin (Subscriptions -> Subscription
plans); nothing here is a product decision. This is the ONE place code reads
seed defaults from: SubscriptionPlan.get_free() (self-heal if the Free row is
missing), the grant_plan() test fixture and migration 0008. Nothing else may
carry a price, storage, collection or video figure.

Limits: None = unlimited; video_minutes 0 = no video allowed.
"""
PLAN_SEED = {
    'free': {
        'name': 'Free', 'price': 0, 'storage_gb': 3,
        'max_collections': 10, 'video_minutes': 0,
        'original_download': False, 'watermark': False, 'branding': False,
    },
    'basic': {
        'name': 'Basic', 'price': 499, 'storage_gb': 20,
        'max_collections': None, 'video_minutes': 0,
        'original_download': False, 'watermark': False, 'branding': False,
    },
    'pro': {
        'name': 'Pro', 'price': 1499, 'storage_gb': 100,
        'max_collections': None, 'video_minutes': 60,
        'original_download': True, 'watermark': True, 'branding': True,
    },
    'studio': {
        'name': 'Studio', 'price': 2999, 'storage_gb': 500,
        'max_collections': None, 'video_minutes': 120,
        'original_download': True, 'watermark': True, 'branding': True,
    },
}
