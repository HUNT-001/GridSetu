function [v, ibr, it] = bfs_loadflow(net, s, tol, maxit)
%BFS_LOADFLOW Backward/forward sweep load flow on a radial network.
%   s     complex load per node in per unit (consumption positive), column vector
%   v     node voltages (per unit), ibr branch currents (branch k feeds node k)
%   Children always have higher node numbers than their parent.

n = numel(s);
v = net.v_src * ones(n, 1);
for it = 1:maxit
    inode = conj(s ./ v);
    ibr = inode;
    for k = n:-1:2                                   % backward sweep: sum currents
        ibr(net.parent(k)) = ibr(net.parent(k)) + ibr(k);
    end
    vnew = zeros(n, 1);
    vnew(1) = net.v_src - net.z(1) * ibr(1);         % forward sweep: voltage drops
    for k = 2:n
        vnew(k) = vnew(net.parent(k)) - net.z(k) * ibr(k);
    end
    if max(abs(vnew - v)) < tol
        v = vnew;
        return;
    end
    v = vnew;
end
error('bfs_loadflow:noConvergence', 'Backward/forward sweep did not converge in %d iterations', maxit);
end
