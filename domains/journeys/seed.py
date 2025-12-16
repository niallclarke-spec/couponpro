"""
Seed example journey for testing.

Creates a 'Broker Sign Up' journey for entrylab tenant with 3 steps:
1. Welcome message
2. Question asking for trading experience  
3. Thank you message with delay
"""

from core.logging import get_logger
from domains.journeys import repo

logger = get_logger(__name__)


def seed_broker_signup_journey(tenant_id: str = 'entrylab', bot_id: str = 'default') -> dict | None:
    """
    Create the Broker Sign Up example journey.
    
    Returns the created journey dict or existing journey if already exists.
    Returns None if creation fails.
    """
    existing = repo.list_journeys(tenant_id)
    for j in existing:
        if j['name'] == 'Broker Sign Up':
            logger.info(f"Journey 'Broker Sign Up' already exists for tenant {tenant_id}")
            return j
    
    journey = repo.create_journey(
        tenant_id=tenant_id,
        bot_id=bot_id,
        name='Broker Sign Up',
        description='Welcome new users from broker partner and collect their info',
        status='draft'
    )
    
    if not journey:
        logger.error("Failed to create journey")
        return None
    
    logger.info(f"Created journey: {journey['id']}")
    
    steps = [
        {
            'step_order': 1,
            'step_type': 'message',
            'config': {
                'text': "Welcome to EntryLab Signals! We're excited to have you here.\n\nAs a valued partner referral, you'll get access to our premium gold trading signals.",
                'delay_seconds': 0
            }
        },
        {
            'step_order': 2,
            'step_type': 'question',
            'config': {
                'text': "Before we get started, we'd love to know: What's your trading experience level?\n\n1. Beginner - Just getting started\n2. Intermediate - A few months of experience\n3. Advanced - Trading for years",
                'delay_seconds': 2,
                'answer_key': 'experience_level'
            }
        },
        {
            'step_order': 3,
            'step_type': 'message',
            'config': {
                'text': "Thanks for sharing! Based on your response, we'll tailor our signals guidance for you.\n\nYou're all set! Use /menu to see available commands.",
                'delay_seconds': 1
            }
        }
    ]
    
    repo.set_steps(tenant_id, journey['id'], steps)
    logger.info(f"Created {len(steps)} steps for journey")
    
    trigger = repo.upsert_trigger(
        tenant_id=tenant_id,
        journey_id=journey['id'],
        trigger_type='telegram_deeplink',
        trigger_config={
            'start_param': 'broker_signup',
            'bot_id': bot_id
        }
    )
    if trigger:
        logger.info(f"Created trigger: {trigger['id']}")
    else:
        logger.error("Failed to create trigger")
    
    repo.update_journey(tenant_id, journey['id'], {'status': 'active'})
    logger.info(f"Activated journey")
    
    return repo.get_journey(tenant_id, journey['id'])


def seed_all_example_journeys():
    """Seed all example journeys."""
    journeys = []
    
    try:
        j = seed_broker_signup_journey('entrylab')
        journeys.append(j)
        logger.info(f"Seeded {len(journeys)} example journeys")
    except Exception as e:
        logger.exception(f"Error seeding journeys: {e}")
    
    return journeys


if __name__ == '__main__':
    print("Seeding example journeys...")
    result = seed_all_example_journeys()
    print(f"Done! Created {len(result)} journeys")
    for j in result:
        print(f"  - {j['name']} (id={j['id']}, status={j['status']})")
