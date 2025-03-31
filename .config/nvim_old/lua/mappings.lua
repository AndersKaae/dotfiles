require "nvchad.mappings"

-- add yours here

local map = vim.keymap.set

map({ "n", "v", "o" }, "½", "$", { desc = "Go to end of line" })

map("n", ";", ":", { desc = "CMD enter command mode" })

map("i", "jk", "<ESC>")

map('i', '<C-L>', 'copilot#Accept("\\<CR>")', {expr = true, replace_keycodes = false })

--

-- map({ "n", "i", "v" }, "<C-s>", "<cmd> w <cr>")
