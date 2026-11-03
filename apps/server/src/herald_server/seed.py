"""Demo workspace: Tripfold, a made-up online luggage brand. Data only; no code knows about it."""

from herald_core.schema import Rule, RuleAction, Urgency, WorkspaceConfig

TRIPFOLD_NAME = "Tripfold"

TRIPFOLD = WorkspaceConfig(
    business_profile=(
        "We sell cabin and check-in luggage, backpacks and travel accessories online across "
        "India. A bad day is a customer at the airport with a broken bag, or a trip tomorrow "
        "and no delivery."
    ),
    topics=[
        "Orders and delivery",
        "Returns and exchanges",
        "Damaged or defective",
        "Warranty claims",
        "Payments and refunds",
        "Product questions",
        "Corporate gifting",
    ],
    important_contacts=["corporate-gifts@bigcorp.example"],
    rules=[
        Rule(
            id="travel-soon",
            name="Travelling soon, order not here",
            when="The customer is travelling in the next 48 hours and the order has not arrived",
            action=RuleAction.ALERT,
        ),
        Rule(
            id="damaged",
            name="Damaged bag",
            when="The bag arrived damaged or broke during use",
            action=RuleAction.SET_URGENCY,
            urgency=Urgency.HIGH,
        ),
        Rule(
            id="corporate",
            name="Corporate order",
            when="The email is about a bulk or corporate order",
            action=RuleAction.ALERT,
        ),
        Rule(
            id="newsletters",
            name="Courier and marketplace newsletters",
            when="It is a newsletter from a courier or a marketplace",
            action=RuleAction.CLOSE,
        ),
    ],
)
