# Multi-Tenant Forex Scheduler Roadmap

## Current State

### Single-Tenant Design
The forex scheduler currently runs for **one tenant only**, configured via the `TENANT_ID` environment variable.

```python
# Current behavior in forex_scheduler.py
resolved_tenant = tenant_id or os.environ.get('TENANT_ID')
if not resolved_tenant:
    logger.error("No tenant_id provided. Set TENANT_ID env var...")
    return
```

### Why Single-Tenant?
The forex scheduler runs **continuous background tasks** that cannot be done in a simple loop:
- Price monitoring every 1 minute
- Signal guidance updates every 1 minute
- Stagnant signal re-validation
- Morning briefings at specific times
- Daily/weekly recaps

These require a long-running `run_forever()` loop per tenant.

## Problem Statement

When a new tenant signs up and needs forex signals:
1. Their signals won't process because the scheduler only runs for `entrylab`
2. Someone must manually add `TENANT_ID=new_tenant` to production config
3. Only ONE tenant can be served at a time per server instance

## Proposed Solution: Tenant Orchestrator

### Architecture Overview
```
┌─────────────────────────────────────────────────────────────┐
│                    Leader Instance                           │
├─────────────────────────────────────────────────────────────┤
│  TenantOrchestrator                                         │
│  ├── Discovers active tenants from database                 │
│  ├── Spawns ForexSchedulerRunner per tenant                 │
│  ├── Monitors health via heartbeats                         │
│  └── Restarts failed schedulers                             │
├─────────────────────────────────────────────────────────────┤
│  Tenant: entrylab          │  Tenant: newtenant            │
│  ├── ForexSchedulerRunner  │  ├── ForexSchedulerRunner     │
│  ├── run_forever()         │  ├── run_forever()            │
│  └── [Price, Guidance...]  │  └── [Price, Guidance...]     │
└─────────────────────────────────────────────────────────────┘
```

### Implementation Steps

#### Phase 1: Tenant Discovery
Create a function to discover tenants that need forex scheduling:

```python
# core/tenant_discovery.py
def get_forex_enabled_tenants() -> List[str]:
    """Get tenants with active forex bot configuration."""
    with db.db_pool.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT t.id 
            FROM tenants t
            JOIN tenant_bot_connections tbc ON t.id = tbc.tenant_id
            WHERE tbc.bot_role = 'signal_bot'
        """)
        return [row[0] for row in cursor.fetchall()]
```

#### Phase 2: Tenant Orchestrator
```python
# core/tenant_orchestrator.py
class TenantOrchestrator:
    def __init__(self):
        self.schedulers: Dict[str, asyncio.Task] = {}
        self.heartbeats: Dict[str, datetime] = {}
    
    async def run(self):
        """Main orchestrator loop."""
        while True:
            # Discover tenants
            tenants = get_forex_enabled_tenants()
            
            # Start schedulers for new tenants
            for tenant_id in tenants:
                if tenant_id not in self.schedulers:
                    self.spawn_scheduler(tenant_id)
            
            # Stop schedulers for removed tenants
            for tenant_id in list(self.schedulers.keys()):
                if tenant_id not in tenants:
                    self.stop_scheduler(tenant_id)
            
            # Health check
            self.check_health()
            
            await asyncio.sleep(60)
    
    def spawn_scheduler(self, tenant_id: str):
        """Spawn a scheduler for a tenant."""
        task = asyncio.create_task(
            self.run_tenant_scheduler(tenant_id)
        )
        self.schedulers[tenant_id] = task
        logger.info(f"Spawned scheduler for tenant: {tenant_id}")
    
    async def run_tenant_scheduler(self, tenant_id: str):
        """Run scheduler for a single tenant with heartbeat."""
        runtime = TenantRuntime(tenant_id=tenant_id)
        scheduler = ForexSchedulerRunner(runtime)
        
        # Heartbeat callback
        async def heartbeat():
            self.heartbeats[tenant_id] = datetime.utcnow()
        
        await scheduler.run_forever(heartbeat_callback=heartbeat)
```

#### Phase 3: Heartbeat & Health Monitoring
```python
def check_health(self):
    """Restart unhealthy schedulers."""
    now = datetime.utcnow()
    for tenant_id, last_heartbeat in self.heartbeats.items():
        if (now - last_heartbeat).total_seconds() > 300:  # 5 min timeout
            logger.warning(f"Scheduler {tenant_id} unhealthy, restarting")
            self.stop_scheduler(tenant_id)
            self.spawn_scheduler(tenant_id)
```

#### Phase 4: Bootstrap Integration
Update `core/bootstrap.py` to use orchestrator:

```python
def start_forex_scheduler_orchestrator():
    """Start the multi-tenant forex scheduler."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    orchestrator = TenantOrchestrator()
    loop.run_until_complete(orchestrator.run())
```

### Resource Considerations

#### Memory
- Each tenant scheduler uses ~50MB
- 10 tenants = ~500MB additional memory
- Monitor and scale as needed

#### Database Connections
- Each tenant needs its own connection for price monitoring
- Pool size should be: (num_tenants * 2) + base_connections
- Currently using pool of 5-20; may need to increase

#### Rate Limits
- Telegram: 30 messages/second globally
- Twelve Data: Check API limits per key
- May need per-tenant API keys for scaling

### Migration Plan

1. **Deploy with backward compatibility**
   - Keep `TENANT_ID` env var support
   - If set, run single-tenant mode (current behavior)
   - If not set, run orchestrator mode

2. **Test with single tenant first**
   - Remove `TENANT_ID` from production
   - Verify orchestrator discovers and runs `entrylab`

3. **Add second tenant**
   - Configure new tenant's Signal Bot in Connections tab
   - Verify orchestrator spawns their scheduler

4. **Monitor and iterate**
   - Watch memory usage
   - Check for race conditions
   - Add metrics/alerts

### Code Changes Required

| File | Change |
|------|--------|
| `core/tenant_discovery.py` | New file for tenant discovery |
| `core/tenant_orchestrator.py` | New file for orchestrator |
| `forex_scheduler.py` | Add heartbeat callback support |
| `core/bootstrap.py` | Switch to orchestrator mode |
| `db.py` | Increase pool size |

### Estimated Effort
- Phase 1 (Discovery): 30 minutes
- Phase 2 (Orchestrator): 1-2 hours
- Phase 3 (Health): 30 minutes
- Phase 4 (Integration): 30 minutes
- Testing: 1 hour

**Total: ~4 hours**

### When to Implement
Implement when:
1. You're ready to onboard a second forex tenant
2. You need forex signals for multiple tenants simultaneously
3. Current single-tenant approach becomes a bottleneck

Until then, the current `TENANT_ID` approach works fine for `entrylab`.
