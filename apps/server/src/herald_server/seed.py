"""Demo workspace: Tripfold, a made-up online luggage brand. Data only; no code knows about it."""

from herald_core.schema import Rule, RuleAction, Topic, Urgency, WorkspaceConfig

TRIPFOLD_NAME = "Tripfold"

TRIPFOLD = WorkspaceConfig(
    business_profile=(
        "We sell cabin and check-in luggage, backpacks and travel accessories online across "
        "India. A bad day is a customer at the airport with a broken bag, or a trip tomorrow "
        "and no delivery."
    ),
    topics=[
        Topic(
            name="Orders and delivery",
            meaning="where an order is, late or missing parcels, address changes",
        ),
        Topic(
            name="Returns and exchanges",
            meaning="sending back an unused bag, or swapping size or colour",
        ),
        Topic(
            name="Damaged or defective",
            meaning="arrived broken, or broke within 30 days of delivery",
        ),
        Topic(
            name="Warranty claims",
            meaning="broke after 30 days, under the 2-year warranty",
        ),
        Topic(
            name="Payments and refunds",
            meaning="charges, failed payments, refund status",
        ),
        Topic(
            name="Product questions",
            meaning="sizes, airline cabin limits, materials, before buying",
        ),
        Topic(
            name="Corporate gifting",
            meaning="bulk or branded orders from companies",
        ),
    ],
    facts=[
        "Returns are accepted within 7 days of delivery, unused and with tags.",
        "Every bag has a 2-year warranty on wheels, zips and handles.",
        "Metro orders arrive in 2-4 days, other cities in 5-7 days.",
        "Refunds reach the original payment method 5-7 days after the return is picked up.",
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
