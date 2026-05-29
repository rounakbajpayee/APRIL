\# APRIL Runtime Contract Design v1



Status: Canonical

Phase: Post-surface-migration consolidation

Related commits:



\* `f5e077e` — stabilize surface runtime state propagation and tracing

\* `7913f10` — introduce RuntimeStateSink protocol and remove bridge shim

\* `bbab670` — remove obsolete migration diagnostics



\---



\# 1. Context



The APRIL surface migration originally began as a UI modernization effort but evolved into a broader runtime consolidation exercise.



The old architecture centered around `widget.py` and widget-style APIs:



```text

InputHandler

→ widget.py

→ widget state + rendering

```



The new architecture is surface-native and event-driven:



```text

InputHandler

→ RuntimeStateSink

→ APRILBridge

→ APRILCore

→ surface runtime

```



The migration was stabilized after deterministic TRACE boundary instrumentation isolated the root cause of the instability to a missing `\_set\_widget\_state` implementation on `InputHandler`.



The bridge architecture itself ultimately proved healthy:



\* Qt queued delivery healthy

\* bridge lifecycle healthy

\* state propagation healthy

\* surface rendering healthy



The final consolidation goal became:



\* remove fake widget semantics

\* remove transitional compatibility layers

\* establish a minimal explicit runtime boundary

\* preserve deterministic runtime behavior

\* avoid overengineering



\---



\# 2. Canonical Runtime Boundary



The canonical runtime contract is now:



```text

InputHandler

→ RuntimeStateSink

→ APRILBridge

→ APRILCore

→ surface runtime

```



`InputHandler` owns runtime input capture and runtime state emission.



`APRILBridge` owns:



\* thread-safe runtime → Qt transition

\* queued signal delivery

\* surface state forwarding



`APRILCore` owns:



\* canonical runtime state authority

\* state propagation

\* state change signaling



\---



\# 3. RuntimeStateSink



```python

from typing import Protocol, runtime\_checkable





@runtime\_checkable

class RuntimeStateSink(Protocol):

&#x20;   def set\_state(self, state: str) -> None:

&#x20;       ...

```



This is intentionally tiny.



The runtime contract exists solely to communicate runtime state transitions from runtime systems into the surface runtime.



No rendering semantics belong here.



No widget semantics belong here.



No Qt dependencies belong here.



No UI ownership belongs here.



\---



\# 4. Why The Interface Is Minimal



The migration intentionally avoided recreating `widget.py` under a new name.



Only one runtime responsibility currently belongs at this boundary:



| Method             | Purpose                                          |

| ------------------ | ------------------------------------------------ |

| `set\_state(state)` | Notify the runtime surface of a state transition |



Everything else:



\* transcripts

\* tasks

\* logs

\* overlays

\* notifications

\* rendering

\* animations



is driven elsewhere by canonical runtime systems.



\---



\# 5. What Explicitly Does NOT Belong Here



The following were intentionally excluded:



| Excluded Item              | Reason                                      |

| -------------------------- | ------------------------------------------- |

| `add\_text\_output()`        | Dead widget-era path                        |

| `set\_transcript()`         | Owned by runtime orchestration              |

| `set\_task()`               | Owned by runtime orchestration              |

| `append\_log()`             | Observability concern, not runtime boundary |

| widget refresh/config APIs | Obsolete widget-era coupling                |

| rendering/overlay APIs     | Surface-layer concern                       |

| Qt imports                 | Runtime boundary must remain UI-agnostic    |



\---



\# 6. RuntimeStateSink vs Direct Bridge Coupling



A direct `InputHandler → APRILBridge` dependency was intentionally avoided.



Instead:



\* `InputHandler` depends only on a tiny runtime contract

\* `APRILBridge` satisfies the protocol structurally

\* no shim or adapter layer remains



This preserves:



\* cleaner testing boundaries

\* future observability insertion points

\* future headless/runtime tooling flexibility

\* lower coupling pressure



while remaining lightweight.



No framework-style abstraction system was introduced.



\---



\# 7. Removed Migration Residue



The following transitional systems were removed during consolidation:



| Removed                             | Reason                                         |

| ----------------------------------- | ---------------------------------------------- |

| `\_BridgeShim`                       | No longer needed once RuntimeStateSink existed |

| `\_widget\_ref` branches              | Dead widget-era compatibility residue          |

| `\_start\_surface\_system()`           | Dead Phase 2 migration artifact                |

| `\_schedule\_widget\_config\_refresh()` | Widget-era config path                         |

| `AudioRecorder.\_set\_widget\_state`   | Dead copy-paste ghost                          |

| `add\_text\_output` fallback path     | No longer used in surface runtime              |

| `\_diag\_widget\_start.py`             | Migration diagnostics artifact                 |

| `\_diag\_widget\_start.log`            | Migration diagnostics artifact                 |



\---



\# 8. Stabilization Methodology



The migration was stabilized using deterministic TRACE boundary instrumentation:



```text

TRACE1 INPUT

TRACE2 SHIM

TRACE3 BRIDGE emit

TRACE4 BRIDGE APPLY

TRACE5 CORE

TRACE6 ANCHOR

TRACE7 repaint

```



This converted the migration from speculative debugging into deterministic causal tracing.



The critical lesson from the migration:



```text

trace-first

hypothesis-second

fix-third

```



\---



\# 9. Architectural Outcomes



The migration produced several durable architectural assets:



| Asset                      | Purpose                             |

| -------------------------- | ----------------------------------- |

| `RuntimeStateSink`         | Canonical runtime boundary          |

| `test\_surface\_only.py`     | Isolated surface regression harness |

| TRACE boundary methodology | Primitive observability foundation  |

| Surface-native runtime     | Canonical runtime ownership         |



\---



\# 10. Future Observability Direction



The runtime contract was intentionally designed to support lightweight observability layering later.



Planned observability principles:



```text

normal

debug

audit

```



Criticality-tiered tracing is planned:



\* Tier 1: runtime spine

\* Tier 2: subsystem state

\* Tier 3: cosmetic/runtime noise



The system intentionally avoids:



\* cloud telemetry

\* heavyweight infrastructure

\* always-on verbose tracing

\* operational complexity



The observability model is intended to remain:



\* local-first

\* lightweight

\* deterministic

\* developer-oriented



\---



\# 11. Current Canonical Runtime State



The APRIL runtime is now:



\* surface-native

\* deterministic

\* bridge-driven

\* event-oriented

\* observability-ready



The migration is considered operationally complete.



Remaining work belongs to:



\* observability foundation

\* feature growth

\* runtime polish

\* subsystem expansion



—not runtime rescue/debugging.



