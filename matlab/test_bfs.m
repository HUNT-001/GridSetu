function test_bfs()
%TEST_BFS Checks bfs_loadflow against a case solved by hand.
%   One load S = P + jQ fed from a source V1 through impedance z = R + jX.
%   Exact receiving-end voltage magnitude from the quadratic
%     |V2|^4 + (2(PR + QX) - |V1|^2) |V2|^2 + |z|^2 |S|^2 = 0   (larger root).

V1 = 1.0; z = complex(0.02, 0.04); S = complex(0.8, 0.3);
b = 2 * (real(S) * real(z) + imag(S) * imag(z)) - V1^2;
c = abs(z)^2 * abs(S)^2;
v2_exact = sqrt((-b + sqrt(b^2 - 4 * c)) / 2);

net.parent = [0; 1];
net.z = [complex(0, 0); z];      % ideal source connection, then the line
net.v_src = V1;
[v, ibr] = bfs_loadflow(net, [0; S], 1e-12, 100);
err = abs(abs(v(2)) - v2_exact);
loss_err = abs(abs(ibr(2))^2 * real(z) - (V1 * abs(ibr(2)) * cos(angle(V1) - angle(ibr(2))) - real(S)));
fprintf('test_bfs: |V2| = %.10f, exact %.10f, error %.1e; loss check error %.1e\n', abs(v(2)), v2_exact, err, loss_err);
assert(err < 1e-9, 'bfs_loadflow does not match the hand-calculated voltage');
assert(loss_err < 1e-9, 'line loss does not match sending-end minus received power');
fprintf('test_bfs: PASS\n');
end
