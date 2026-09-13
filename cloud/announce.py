"""Report the actual runner setup before Docker starts the calculations."""
from run import api

api('context')
api('event', {'event': {'state': 'phase', 'title': 'Downloading the Docker image',
                      'message': 'The GitHub runner is preparing the preserved software for this execution.'}})
