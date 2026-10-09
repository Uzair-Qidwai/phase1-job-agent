"""Offline Agents SDK model harness; never calls a provider."""
import json
from agents import Model, ModelResponse
from agents.usage import Usage
from openai.types.responses import ResponseOutputMessage, ResponseOutputText


def message(payload):
    return ResponseOutputMessage(id="msg_1", type="message", role="assistant", status="completed",
                                 content=[ResponseOutputText(type="output_text", text=json.dumps(payload), annotations=[])])


class FakeModel(Model):
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.inputs = []

    async def get_response(self, *args, **kwargs):
        self.inputs.append(kwargs.get("input"))
        value = self.outputs.pop(0)
        if isinstance(value, Exception):
            raise value
        return ModelResponse(output=[value], usage=Usage(requests=1, input_tokens=100, output_tokens=20), response_id=None)

    async def stream_response(self, *args, **kwargs):
        raise NotImplementedError
        yield

