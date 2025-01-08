local on_attach = require("nvchad.configs.lspconfig").on_attach
local on_init = require("nvchad.configs.lspconfig").on_init
local capabilities = require("nvchad.configs.lspconfig").capabilities

local lspconfig = require "lspconfig"

local servers = { "html", "cssls", "pyright", "gopls", "omnisharp" }

for _, lsp in ipairs(servers) do
  if lsp == "omnisharp" then
    lspconfig.omnisharp.setup {
      cmd = {
        vim.fn.stdpath("data") .. "/mason/bin/omnisharp",
        "--languageserver",
        "--hostPID", tostring(vim.fn.getpid())
      },
      on_attach = on_attach,
      on_init = on_init,
      capabilities = capabilities,
      root_dir = lspconfig.util.root_pattern("*.sln", "*.csproj") or vim.fn.getcwd(),
    }
  else
    lspconfig[lsp].setup {
      on_attach = on_attach,
      on_init = on_init,
      capabilities = capabilities,
    }
  end
end
