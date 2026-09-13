"""Report the actual runner setup before Docker starts the calculations."""
from run import api, TemporaryAPIError

try:
    api('context')
    api('event', {'event': {'state': 'phase', 'title': 'Downloading the Docker image',
                          'message': 'The GitHub runner is preparing the preserved software for this execution.'}})
except TemporaryAPIError:
    # This optional setup message must not prevent the real Docker execution.
    print('Setup status is temporarily unavailable; continuing with the Docker image.', flush=True)
