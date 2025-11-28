# Using Claude Agent SDK with Claude Code Max Subscription (Workaround)

## Important Disclaimer

This workaround is **NOT officially supported** by Anthropic. The official documentation explicitly states that third-party developers should not apply Claude.ai rate limits for their products built on the Claude Agent SDK. Use at your own risk.

## Official Recommendation

Anthropic recommends using an API key from console.anthropic.com for the Claude Agent SDK, which uses pay-per-use API pricing.

## Workaround Instructions

If you have a Claude Code Max subscription and want to attempt using it with the Claude Agent SDK despite the warnings above, some users have reported success with the following approach:

### TypeScript SDK

Instead of setting `ANTHROPIC_API_KEY`, use the `CLAUDE_CODE_OAUTH_TOKEN` environment variable:

```bash
export CLAUDE_CODE_OAUTH_TOKEN="your-token-here"
```

This approach was reported working on SDK version 0.1.8 or later.

### Python SDK

The Python SDK reportedly integrates more seamlessly with Claude Code credentials by using the system-installed `claude` binary. Ensure Claude Code is installed and authenticated with your Max subscription.

## Limitations and Risks

1. **Not Officially Supported**: This method is not documented in official Anthropic documentation
2. **May Violate Terms**: The SDK documentation states this usage pattern is not approved
3. **Subject to Breaking Changes**: Could stop working at any time without notice
4. **Rate Limit Concerns**: Using subscription rate limits for SDK-based products may not be permitted
5. **No Support**: Anthropic support will not help troubleshoot issues with this approach

## Getting Your Token

To obtain the OAuth token from an authenticated Claude Code installation:

1. Ensure Claude Code is installed and authenticated with your Max subscription
2. The token is typically stored in Claude Code's configuration directory
3. Check your environment or Claude Code settings for the token value

## Alternative: Use Official API Authentication

For production use or reliability, it's strongly recommended to:

1. Visit https://console.anthropic.com
2. Generate an API key
3. Set `ANTHROPIC_API_KEY` environment variable
4. Use pay-per-use API pricing instead of subscription limits

This provides:
- Official support
- Guaranteed stability
- Clear terms of service compliance
- Better error handling and documentation

## References

- GitHub Issue discussing this: https://github.com/anthropics/claude-agent-sdk-typescript/issues/11
- Official documentation: https://docs.claude.com/en/api/agent-sdk/overview
- Claude Code with Pro/Max plans: https://support.claude.com/en/articles/11145838-using-claude-code-with-your-pro-or-max-plan
