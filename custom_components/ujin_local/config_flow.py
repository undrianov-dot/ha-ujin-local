"""Config flow for UJIN Local."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import DEFAULT_PORT, DOMAIN


class UjinLocalConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            return self.async_create_entry(title="UJIN Local", data=user_input)

        schema = vol.Schema(
            {vol.Optional("port", default=DEFAULT_PORT): vol.All(int, vol.Range(1, 65535))}
        )
        return self.async_show_form(step_id="user", data_schema=schema)
