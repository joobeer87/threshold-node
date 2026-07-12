# Aurora framework easter egg

Threshold carries a small, public-safe signature from the Aurora framework: **authority
before autonomy**. It is deliberately an easter egg, not a claim that the private AuroraOS
control plane is bundled into this repository.

## Discovery

Run the local node and open:

```text
/.well-known/aurora
```

The hidden route is omitted from the generated API schema. It returns a static,
non-sensitive receipt describing four public design principles:

- the owner remains the authority;
- model output is a proposal;
- uncertain or unauthorized actions fail closed;
- important decisions leave a bounded receipt.

Its safety booleans explicitly say that no secret material was returned, no unauthorized
action was executed, and no private control plane was exposed.

## Video moment

After the no-go denial, hold on the terminal or receipt for two seconds:

```text
AURORA // AUTHORITY BEFORE AUTONOMY
BOUNDARY HELD · RECEIPT CLEAN
```

Keep it subtle. The main story remains Threshold's owner-held permission boundary. The
easter egg should reward curious judges without introducing a second product narrative.

## Public boundary

Do not copy private AuroraBrain memories, control-plane schemas, connector configuration,
operator routes, internal hostnames, or deployment details into this repo. The signature
contains only general governance principles already demonstrated by Threshold's public
code and tests.
