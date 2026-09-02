# Learning checkpoint 1: Explain the reactive battery

This checkpoint is intentionally assigned to you. Complete it before presenting the project in an interview.

## A. Run the default scenario

Use:

```text
Date: 1 June 2025
Portfolio: Mixed
Capacity: 100 MW
Wind share: 50%
Battery: 25 MW / 2 hours = 50 MWh
Initial SOC: 50%
Round-trip efficiency: 90%
```

Download the scenario CSV.

## B. Verify four settlement periods manually

Choose:

1. one period with renewable surplus;
2. one period with renewable deficit;
3. one power-limited period;
4. one energy-limited period, if present.

For each one, write down:

```text
actual MW
forecast MW
forecast error MW
requested battery response MW
allowed response after power constraint
allowed response after SOC constraint
charge or discharge MW
SOC before and after
firmed delivery MW
residual error MW
```

Use a 0.5-hour interval and remember that charging adds \(P\eta_c\Delta t\) to SOC, while discharging removes \(P\Delta t/\eta_d\).

## C. Explain the practical trade-offs

Be able to answer in your own words:

- Why can a 4-hour battery outperform a 1-hour battery at the same MW?
- Why can increasing MWh fail to help when the battery is power-limited?
- Why does a high initial SOC help deficits but reduce charging headroom?
- Why is a mixed wind/solar portfolio potentially easier to firm than either technology alone?
- Why is this a portfolio benchmark and not a site-specific design?

## D. Interview-ready explanation

Prepare a 60-second explanation covering:

1. the forecast error being managed;
2. the physical battery constraints;
3. the reactive strategy's information boundary;
4. the metrics used to compare configurations;
5. the main limitation of scaling national capacity factors to a virtual portfolio.
