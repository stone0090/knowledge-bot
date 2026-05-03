[

![图像](https://cdn.gooo.ai/web-images/c1af7137c58e0d76bcbb5f3d0d43ab8b9247e6ed6df53f279832b84ad76fc9af)
](https://x.com/sitinme/article/2029733206313030146/media/2029384904702869507)

玩龙虾最基础的是能和它对上话，后面慢慢可以探索更多玩法，给它装上各种各样的技能，让它能做更多事情，最大程度提高你的效率。

而且用的过程中遇到的问题、踩过的坑，全让它记录下来，自己迭代自己，慢慢你的龙虾就越养越智能，越养越好用。

但刚装好的时候可能会遇到不少问题，比如推特看不了，公众号文章反爬严重也读不了。好在各路大佬迭代速度太快了，你遇到的问题大家基本都遇到过，而且已经有人给出了解决方案。

这段时间搜罗了一批好用的工具和技巧，装上之后龙虾的工作效率明显上了一个台阶。整理几个分享给大家。

之前为了让龙虾能上网，要装好几个工具：读推特的、爬网页的、搜 Reddit 的，每个都要单独装、单独维护。后来发现居然有一个工具全搞定的 Agent Reach。

安装方式特别简单，直接跟龙虾说一句话：

[

![图像](https://cdn.gooo.ai/web-images/d4cc51fe5cf1fd9e5590aa76fe9123e7eb69411ee946256cd901596e91347aad)
](https://x.com/sitinme/article/2029733206313030146/media/2029385232039006208)

装完之后能干什么？零配置就能用的：任意网页内容读取、YouTube 字幕提取、RSS 订阅、GitHub 公开仓库。

配上 Cookie 之后还能解锁 Twitter、小红书、抖音、LinkedIn、Boss直聘。

配个代理还能上 Reddit、B站、Exa 全网语义搜索。

它的设计思路很赞，不自己造轮子，把社区里最好的工具帮你选好装上。底层用的 Jina Reader 读网页、yt-dlp 搞视频（这个 148K Star，YouTube 加 B站加 1800 个站通吃）、xreach 读推特。

和现有方案的对比：

读网页这块，之前我是用 Playwright 启动一个完整的浏览器去抓。能用，但太重了，吃内存。Agent Reach 底层用的 Jina Reader，一个 curl 请求就拿回干净的 Markdown 文本，90% 的场景根本不需要启动浏览器。

只有那种必须 JS 渲染或者要截图交互的页面，才需要 Playwright 出场。

推特这块，我之前单独装了 bird CLI，用得挺好的，定时任务也都基于它写的。Agent Reach 里的 xreach 功能类似，老工具好用就继续用。

还有之前让龙虾帮我看一个视频，它是真的看不了。有了 yt-dlp 一条命令就把字幕拉下来了，YouTube 和 B站通吃。

[

![图像](https://cdn.gooo.ai/web-images/5e1fa1da04939aa87dff1352ab1edce4a163b53546a16f239e4028bc32746da1)
](https://x.com/sitinme/article/2029733206313030146/media/2029385324531720192)

Agent Reach 覆盖了大部分平台，但有一个它管不到：微信公众号。

[

![图像](https://cdn.gooo.ai/web-images/73ea9f61c5853d333242fdffe9cd20d31cfe50ec4673250ee8ef369f61cb578c)
](https://x.com/sitinme/article/2029733206313030146/media/2029385406056415235)

每天刷到好的公众号文章，链接直接丢给龙虾，让它提炼要点存下来。写文章需要参考素材，丢一堆链接让它帮我整理。

给大家看个有意思的，龙虾会瞎猜，不能完全相信小龙虾的话。

[

![图像](https://cdn.gooo.ai/web-images/26f15eeea94f4950bb676feee5937d1744e9d56a453774f197983c06c0ec9d60)
](https://x.com/sitinme/article/2029733206313030146/media/2029385484787757056)

现在信息特别多，光靠自己根本学不完，最好的方式就是让 AI 学，看到好的内容发给它，龙虾会自动读全文、提炼核心要点、然后写进自己的 MEMORY.md 记忆文件里。

自我迭代。

[

![图像](https://cdn.gooo.ai/web-images/b7dc992e2de2e904e4029de056544dc971c7aac9cf12f8119a97fbf00783bfbf)
](https://x.com/sitinme/article/2029733206313030146/media/2029385555105226752)

LLM 不等于大脑，LLM 等于智商。完整的智能体应该是智商加上记忆加上肌肉记忆加上生物钟加上感知器官。还有一句话它自己标了重点："你认为你记住的东西，那是你的幻觉。不靠脑子，靠文件。"

刷到任何好文章，顺手把链接丢给龙虾。日积月累，它越来越懂我关注的领域。

第一步，收藏。在 X、公众号、知乎上看到好的工作流、方法论、SOP，先收藏下来。

第二步，转成 Skill。把内容整理成 SKILL.md 格式，其实就是一个 Markdown 文件，告诉龙虾在什么场景下、按什么步骤执行。

第三步，执行。下次遇到类似场景，龙虾自动调用这个 Skill。

[

![图像](https://cdn.gooo.ai/web-images/74ad9dbc89c8c64dd87f8ec8e76b23acddc00d59d115a0343ceac758038b3083)
](https://x.com/sitinme/article/2029733206313030146/media/2029385637284200454)

比如你看到一个大佬分享的"写公众号爆款标题的 10 个公式"，转成 Skill 后，以后让龙虾帮你起标题，它就会自动套用这些公式。

说白了就是：全网最聪明的人总结的经验，你一键下载到自己的 AI 员工脑子里。

安全方面有一个建议：先装 Skill Vetter，再装其他技能。ClawHub 上现在有 5700 多个社区技能，鱼龙混杂。Skill Vetter 能在安装前做安全审计，帮你识别恶意指令和风险代码。

另外推荐关注 GitHub 上的 awesome-openclaw-skills 仓库，5.3K Star，从 5705 个技能里精选了 2868 个高质量的，过滤掉了垃圾和恶意代码。

龙虾是个好东西，但它不会自己变强。你得给它装工具，喂知识，犯错了给反馈。

后面还会持续分享养虾过程中摸索出来的实战技巧，感兴趣的可以关注。

如果你对 OpenClaw 感兴趣，或者在实践中遇到问题，欢迎加入 OpenClaw 中文交流群。

99 元入群，送 $50 [aigocode.com](https://aigocode.com/) 算力额度。群里都是实际在用 OpenClaw 的玩家，每天分享使用技巧和踩坑经验，氛围很活跃。

[

![图像](https://cdn.gooo.ai/web-images/3165833e5666da80feb04e475b27d4d3b043ff6983d30ad57bd8dbb942cbf052)
](https://x.com/sitinme/article/2029733206313030146/media/2029385851659272193)