"""Stream large JSON without changing the browser's JSON API contract."""
from starlette.responses import JSONResponse, StreamingResponse


class HostedJSONResponse(JSONResponse):
    async def __call__(self, scope, receive, send):
        if len(self.body) < 1_000_000:
            return await super().__call__(scope, receive, send)

        async def chunks():
            for offset in range(0, len(self.body), 64 * 1024):
                yield self.body[offset:offset + 64 * 1024]

        response = StreamingResponse(chunks(), status_code=self.status_code, background=self.background)
        response.raw_headers = [(name, value) for name, value in self.raw_headers if name.lower() != b"content-length"]
        return await response(scope, receive, send)
