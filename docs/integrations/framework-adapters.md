# Use your existing model client

Load a registry once at startup, render the inputs for each request, and validate the response before updating application state. The library does not create a client or manage credentials, retries, or timeouts.

`rendered.to_messages_list()` returns a list of dictionaries with `role` and `content` fields. Pass this list to clients that accept that message format. For clients with message classes, map each role to the client's corresponding message type and preserve message order and content.

```python
rendered = contract.render(inputs)
messages = rendered.to_messages_list()
```

Call your existing client with `messages`, request JSON output if supported, and inspect the completion status. Reject refusals, truncated responses, and unexpected tool calls before passing the response text to validation:

```python
validated = contract.validate_output(response_text)
```

Use `validated` to update your application's state. Catch `InputValidationError` and `OutputValidationError` at the boundary where your application handles invalid requests and failed model calls.

For `llm-gateway-sdk`, use the [gateway adapter](gateway-sdk.md) to map requests and check completion states. For evaluations, use the [Promptfoo bridge](promptfoo.md) to share the application's contract renderer.
