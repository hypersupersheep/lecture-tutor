# Compound interest

- [Pretest](#pretest)
- [Interest on interest](#interest-on-interest)

How to read this note: only what the lecturer said and the slides show, in lecture order; quotes are verbatim, (slide N) is the footer number and (mm:ss) the recording time.

## Pretest

<!-- tal:pretest -->
1. A friend claims that compound interest is just a higher rate than simple interest. Why is this wrong?

<details><summary>Answer</summary>

The rate can be the same; compounding changes what it applies to: the balance, which includes the interest already earned (slide 1, 0:36).

</details>

2. One account pays its quoted yearly rate in four instalments, another pays the same quoted rate in two. Which earns more over a full year, and why?

<details><summary>Answer</summary>

The one with four instalments: more payments a year give a higher effective annual rate, even with the same quoted rate (slide 3, 2:33).

</details>

3. A deposit of 100 earns 5% a year, compounded yearly. What does it hold after 10 years?

<details><summary>Answer</summary>

About 162.89: the balance is 100 times 1.05 to the power 10 (slide 2, 1:39).

</details>
<!-- /tal:pretest -->

## Interest on interest

*(slides 1–3, 0:00–2:58)*

The same yearly rate can be paid in two ways: simple interest on the deposit only, compound interest on "the balance, past interest included" (slide 1, 0:27).

> So last year's interest is now part of the balance, and this year it earns interest too. (0:36)

Each year multiplies the balance by $1+r$, so a deposit $P$ after $n$ years is (slide 2, 1:12)

$$P(1+r)^n \tag{1}$$

At 5%, 100 reaches 162.89 after 10 years, against 150 with simple interest (slide 2, 1:39).

A quoted rate $r$ paid $m$ times a year earns the effective annual rate (slide 3, 2:24)

$$(1+r/m)^m - 1 \tag{2}$$

It rises with $m$, so compare accounts by it (slide 3, 2:42).

<!-- tal:check -->
1. You must rank three savings accounts that pay interest on different schedules. Which single number do you work out for each one?

<details><summary>Answer</summary>

Its effective annual rate, since quoted rates on different schedules cannot be compared directly (slide 3, 2:42).

</details>

2. Why does the compound balance grow by a power of 1 + r rather than by equal steps each year?

<details><summary>Answer</summary>

Each year multiplies a bigger amount by the same 1 + r, because "last year's interest is now part of the balance" (0:36); equal steps would mean interest on the deposit only (slide 2, 1:03–1:21).

</details>
<!-- /tal:check -->
