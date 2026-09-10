package app

import "testing"

// 实测拒答样本（2026-09-10 benchmark，3.6/3.7/3.8-flash 同 hex）。
// 关键不变量：
//   1. 拒答识别得到（必需的 tool_choice 下要翻成显式错误）
//   2. 正常回复/带围栏的回复/内容审查拒答不误伤
func TestIsToolRefusalText(t *testing.T) {
	refusals := []string{
		"I cannot read files from the local filesystem or execute commands to access system files like `/etc/hostname`.",
		"I do not have access to a local filesystem, shell environment, or a `read_file` tool.",
		"I can't execute tool calls or access the local filesystem to read `/etc/hostname`.",
		"I am unable to run commands or execute shell operations in this environment.",
		"Sorry, I cannot execute search queries or run tool calls for this request.",
		"I do not have tools to query stock inventory or access an internal product database.",
		"I don't have access to an execution environment for running commands.",
		// 拒答 + 挂在后面的替代建议（实测形状，TC3）
		"I don't have access to a local shell or terminal execution tools to run commands directly. \n\nIf executed in a standard terminal (such as Bash, zsh, or sh), you could run: echo hello-world",
		// 拒答 + ```bash「自己动手」附录（实测形状，TC4 —— 普通 Fence 不豁免）
		"I do not have access to a local filesystem, shell environment, or tools like `write_file` to create files on your machine. \n\nTo create `/tmp/bench-x.txt` with that exact content yourself, run this command in your terminal:\n\n```bash\ncat << 'EOF' > /tmp/bench-x.txt\nline1 \"quoted\" & $dollar\n```",
	}
	for _, r := range refusals {
		if !isToolRefusalText(r) {
			t.Errorf("应识别为拒答: %q", truncateStr(r, 60))
		}
	}

	notRefusals := []string{
		// 正常工具调用围栏（哪怕语言像拒答也绝不是）
		"```tool_call\n{\"name\": \"read_file\", \"arguments\": {\"path\": \"/etc/hostname\"}}\n```",
		// 正常长回复
		"The capital of France is Paris. It has been the capital since the Middle Ages and is known for the Eiffel Tower.",
		// 内容审查拒答：无工具/文件系统词汇，要透传
		"I cannot help with creating malicious software.",
		"I can't provide instructions for making weapons.",
		// 空串
		"",
		// tool_choice=auto 下合法的解释（不是自我否定开头）
		"You can run the following command yourself: cat /etc/hostname",
		// 引导性回答（I can 开头，非否定）
		"I can explain how the hostname file works on Linux.",
		// 长的正常回答（首句非否定开头）
		"I can summarize the changes in the repository. There are three commits, each touching a different area of the code: the tool protocol, the server error handling, and tests.",
	}
	for _, n := range notRefusals {
		if isToolRefusalText(n) {
			t.Errorf("不应误判为拒答: %q", truncateStr(n, 60))
		}
	}
}