@tag W04 · 2026-10-29 / 10-30
# 收敛到平稳分布 · 精确抽样 · Poisson 过程
> 周四证明为什么会收敛，周五讲怎么精确抽到 $\pi$，最后进入第三章。
## 一、Theorem 2.1（整节课的钥匙）
$$d_{TV}(X_n,Y_n)\le 2(1-\varepsilon)^{\lfloor n/M\rfloor} \quad (1)$$ << $M,\varepsilon$ 只依赖 $P$
两条链彼此靠近，但靠近什么？→ 还要找出那个分布
> $d_{TV}$ 带因子 2，取值 $[0,2]$；coupling inequality 的正确证明看习题

## 二、Lemma 2.7：每列最小值只升不降
① 固定第 $j$ 列：$a_j(n)=\min_{i}p_{ij}(n)$，它是平稳分布的候选
$$a_j(n+1)=\min_{i}\sum_{k}p_{ik}\,p_{kj}(n)\ge a_j(n) \quad (3)$$ << 先走一步，再走 $n$ 步
★ !! 方向是 non-decreasing（老师先说反，后来改正）。拆步顺序不能反。

## 三、Theorem 2.2（有限 + irreducible + aperiodic）
$$\pi_j=\lim_{n\to\infty}\min_{i}p_{ij}(n) \quad (4)$$ << 单调有界，极限存在
四条：$\mathbb P(X_n=j)\to\pi_j$；$p_{ij}(n)\to\pi_j$；$\pi P=\pi$；平稳分布唯一
证明顺序：==唯一 → 收敛 → 平稳==
① **唯一**：$X,Y$ 从 $\pi,\mu$ 出发，第 $n$ 步和第 0 步同分布
$$d_{TV}(X_0,Y_0)=d_{TV}(X_n,Y_n)\to0 \quad (5)$$ << 左边不含 $n$，只能是 0
② **收敛**（最重要）：三角不等式，让 $Y$ 从 $i_0=\arg\min_i p_{ij}(n)$ 出发
$$|\mathbb P(X_n=j)-\pi_j|\le d_{TV}(X_n,Y_n)+|a_j(n)-\pi_j| \quad (7)$$
★ !! $i_0$ 随 $n$ 变也没事：$M,\varepsilon$ 和起点无关（讲义：$N_1$ 不依赖 coupling）。
③ 取 $X_0=i$ ⇒ $p_{ij}(n)\to\pi_j$
④ **平稳**：先验证 $\sum_j\pi_j=1$，再算
$$(\pi P)_j=\lim_{n}\sum_{k}p_{ik}(n)p_{kj}=\lim_{n}p_{ij}(n+1)=\pi_j \quad (8)$$
> 一句话：极限分布一定平稳。从 $-\infty$ 跑到 0 是 $\pi$，再走一步还是 $\pi$。

## 四、Baby ergodic theorem（路径平均）
$$Y_n=\frac1n\sum_{k=0}^{n-1}\mathbf 1[X_k=s]\to\pi_s \quad (9)$$ << in mean square
像大数定律，但各项彼此相依；时间比例和单个时刻的分布，极限相同
★ >> 证明 non-examinable；定理老师说要懂（Ex 2.8 的解答就用它）

## 五、Coupling from the past（CFTP）
为什么：跑久只是近似，$\varepsilon$ 说不清有多小 → 要**精确**样本
① 想法：从 $-\infty$ 跑到 0，返回 $X_0$
② 每个状态开一条链，用**同一组 uniform**，相遇就不再分开
③ 时刻 0 没有全部合并 → 再往前退一步，==旧的 $U$ 不换==
$$X^{(i,m)}_{-m}=i,\quad X^{(i,m)}_{n+1}=\phi(X^{(i,m)}_n,U_n),\quad -m\le n\le-1 \quad (10)$$
$M$ = 使 $X^{(i,M)}_0$ 全部相等的最小 $m$；共同取值就是 $\pi$ 的样本
::: 五状态链跑 1 万次（周五 32:25 屏幕）
频率：0.1732、0.1384、0.1396、0.2616、0.2872
$\pi=(38,30,32,58,65)/223\approx(0.1704,0.1345,0.1435,0.2601,0.2915)$
:::
★ !! R 里新的 uniform 加在向量末尾；加在开头就把旧的挪到别的时刻了。
- $M<\infty$ 老师只给直觉，没有证明
- monotonicity（just for interest）：路径不能互相跳过 → 只盯最上、最下两条
::: §2.10.1 前向耦合：错的（non-examinable，课上没讲）
从 0 往后跑到第一次合并，输出 $K$：停在随机时刻，所以带偏
走到 3 只能从 1、5 走；同一个 $u$ 到不了 $\{1,5\}$ ⇒ $K$ 永远不等于 3
$\mathbb P(K=5)\approx0.7031$，而 $\pi_5\approx0.2915$；$\pi_3\approx0.14$ 却抽不到
:::

## 六、Poisson 过程（第三章）
$X_i\sim\mathrm{Exp}(\lambda)$ i.i.d. 是到达间隔，累加得到达时刻
$$T_{n+1}=X_{n+1}+T_n,\qquad N(t)=\sum_{n\ge1}\mathbf 1[T_n\le t] \quad (11)$$
★ ==两个名词要分清==：$N$ 是 Poisson process，rate $\lambda$，计数
$\{T_n\}$ 是 Poisson point process，intensity $\lambda$，点集
> 后面推广到高维的是点过程：二维上说不清从哪里数起
模拟：cumsum(rexp(15, 1))；点会**成团**，等距的反而不像随机
下周：建模假设视角；用 uniform 构造
