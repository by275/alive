from datetime import date, datetime

from flask.json.provider import DefaultJSONProvider
from plugin import F  # type: ignore # pylint: disable=import-error


class UpdatedJSONProvider(DefaultJSONProvider):
    def default(self, o):
        if isinstance(o, (date, datetime)):
            return o.isoformat()
        return super().default(o)


app = F.app
app.json = UpdatedJSONProvider(app)
