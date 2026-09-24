"""Config flow for UJIN Local."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult

from .const import DEFAULT_PORT, DOMAIN


class UjinLocalConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            return self.async_create_entry(title="UJIN Local", data=user_input)

        return self.async_show_form(step_id="user", data_schema=self._port_schema())

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            return self.async_update_reload_and_abort(entry, data=user_input)

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self._port_schema(entry.data.get("port", DEFAULT_PORT)),
        )

    @staticmethod
    def _port_schema(port: int = DEFAULT_PORT) -> vol.Schema:
        schema = vol.Schema(
            {vol.Required("port", default=port): vol.All(int, vol.Range(1, 65535))}
        )
        return schema
