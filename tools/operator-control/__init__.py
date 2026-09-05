"""No listener is started by this distribution.

A private deployment may wrap ActionBroker in ACL-restricted Unix IPC only after
creating a separate UID/container or choosing a managed policy service.
"""


def build_service(*_args, **_kwargs):
    raise RuntimeError("operator-control service is unconfigured; no listener started")
