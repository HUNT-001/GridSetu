function [theta_o, theta_h, age] = dt_thermal(K, ambient, on, p, step_min)
%DT_THERMAL IEC 60076-7 thermal model of the distribution transformer.
%   Difference equations, sub-stepped (p.solver.thermal_substep_min). K is the load
%   factor (per unit of rating) per 15-minute step, ambient in deg C, on = energized.
%   Returns top-oil and hot-spot temperature at the end of each step, and the mean
%   relative ageing rate V = 2^((theta_h - 98)/6) over each step.

if nargin < 5, step_min = 15; end
tr = p.transformer;
th = tr.thermal;
R = tr.load_loss_w / tr.no_load_loss_w;
d_or = tr.top_oil_rise_k;
d_hr = th.hotspot_gradient_k;
dt = p.solver.thermal_substep_min;
nsub = round(step_min / dt);
n = numel(K);
theta_o = zeros(n, 1); theta_h = zeros(n, 1); age = zeros(n, 1);

k0 = K(1) * on(1);
to = ambient(1) + d_or * ((1 + R * k0^2) / (1 + R))^th.x;          % start in steady state
h1 = th.k21 * d_hr * k0^th.y;
h2 = (th.k21 - 1) * d_hr * k0^th.y;
for t = 1:n
    if on(t)
        k = K(t);
        oil_ss = d_or * ((1 + R * k^2) / (1 + R))^th.x;
    else
        k = 0;
        oil_ss = 0;                                  % de-energized: no losses
    end
    a = 0;
    for s = 1:nsub
        to = to + dt / (th.k11 * th.tau_o_min) * (oil_ss - (to - ambient(t)));
        h1 = h1 + dt / (th.k22 * th.tau_w_min) * (th.k21 * d_hr * k^th.y - h1);
        h2 = h2 + dt / ((1 / th.k22) * th.tau_o_min) * ((th.k21 - 1) * d_hr * k^th.y - h2);
        a = a + 2^((to + h1 - h2 - th.ageing_reference_c) / th.ageing_doubling_k);
    end
    theta_o(t) = to;
    theta_h(t) = to + h1 - h2;
    age(t) = a / nsub;
end
end
