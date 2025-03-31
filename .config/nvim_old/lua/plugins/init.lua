return {
  {
    "stevearc/conform.nvim",
    -- event = 'BufWritePre', -- uncomment for format on save
    config = function()
      require "configs.conform"
    end,
  },

  {
    "neovim/nvim-lspconfig",
    config = function()
      require("nvchad.configs.lspconfig").defaults()
      require "configs.lspconfig"
    end,
  },

  {
    "williamboman/mason.nvim",
    opts = {
      ensure_installed = {
        "lua-language-server",
        "stylua",
        "html-lsp",
        "css-lsp",
        "prettier",
        "pyright",
        "vue-language-server",
        "typescript-language-server",
        "gopls",
        "omnisharp"
      },
    },
  },

  {
    "nvim-treesitter/nvim-treesitter",
    opts = {
      ensure_installed = {
        "vim",
        "lua",
        "vimdoc",
        "html",
        "css",
        "python",
        "javascript",
        "typescript",
        "json",
        "jsonc",
        "yaml",
        "toml",
        "go",
        "c_sharp"
      },
    },
  },

  {
    "github/copilot.vim",
    lazy = false,
    config = function()  -- Mapping tab is already used by NvChad
      vim.g.copilot_no_tab_map = true;
      vim.g.copilot_assume_mapped = true;
      vim.g.copilot_tab_fallback = "";
      -- The mapping is set to other key, see custom/lua/mappings
      -- or run <leader>ch to see copilot mapping section
    end
  },
  {
    "akinsho/bufferline.nvim",
    version = "*", -- Use the latest stable version
    dependencies = "nvim-tree/nvim-web-devicons", -- Optional for file icons
    config = function()
      require("bufferline").setup({
        options = {
          numbers = "none", -- or "ordinal" | "buffer_id" | "both"
          indicator = { style = "icon", icon = "▎" }, -- Or a custom indicator
          modified_icon = "●", -- Icon to show unsaved changes
          show_close_icon = true,
          diagnostics = "nvim_lsp", -- Show LSP diagnostics
          separator_style = "slant", -- Customize separators
        },
      })
    end,
  },
  {
    "folke/todo-comments.nvim",
    lazy = false,
    dependencies = { "nvim-lua/plenary.nvim" },
    opts = {
      -- your configuration comes here
      -- or leave it empty to use the default settings
      -- refer to the configuration section below
    }
  },
  {
    "ray-x/go.nvim",
    dependencies = {  -- optional packages
      "ray-x/guihua.lua",
      "neovim/nvim-lspconfig",
      "nvim-treesitter/nvim-treesitter",
    },
    config = function()
      require("go").setup()
    end,
    event = {"CmdlineEnter"},
    ft = {"go", 'gomod'},
    build = ':lua require("go.install").update_all_sync()' -- if you need to install/update all binaries
  }
}
