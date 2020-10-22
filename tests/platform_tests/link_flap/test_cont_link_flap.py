"""
Tests the continuous link flap in SONiC.

Parameters:
    --orch_cpu_threshold <port> (int): Which port you want the test to send traffic
        to. Default is 3.
"""

import logging
import time
import pytest

from tests.common.helpers.assertions import pytest_assert
from tests.common import port_toggle
from tests.platform_tests.link_flap.link_flap_utils import build_test_candidates, toggle_one_link


pytestmark = [
    pytest.mark.disable_loganalyzer
]

class TestContLinkFlap(object):
    """
    TestContLinkFlap class for continuous link flap
    """

    def test_cont_link_flap(self, request, duthost, fanouthosts, bring_up_fannout_interfaces, perform_config_reload):
        """
        Validates that continuous link flap works as expected

        Test steps:
            1.) Flap all interfaces one by one in 1-3 iteration
                to cause BGP Flaps.
            2.) Flap all interfaces on peer (FanOutLeaf) one by one 1-3 iteration
                to cause BGP Flaps.
            3.) Watch for memory (show system-memory) ,orchagent CPU Utilization
                and Redis_memory.

        Pass Criteria: All routes must be re-learned with < 5% increase in Redis and 
            ORCH agent CPU consumption below threshold after 3 mins after stopping flaps.
        """
        orch_cpu_threshold = request.config.getoption("--orch_cpu_threshold")

        # Record memory status at start
        memory_output = duthost.shell("show system-memory")["stdout"]
        logging.info("Memory Status at start: %s", memory_output)

        # Record Redis Memory at start
        start_time_redis_memory = duthost.shell("redis-cli info memory | grep used_memory_human | sed -e 's/.*:\(.*\)M/\\1/'")["stdout"]
        logging.info("Redis Memory: %s M", start_time_redis_memory)

        # Record ipv4 route counts at start
        start_time_ipv4_route_counts = duthost.shell("show ip route summary | grep Total | awk '{print $2}'")["stdout"]
        logging.info("IPv4 routes at start: %s", start_time_ipv4_route_counts)

        # Record ipv6 route counts at start
        start_time_ipv6_route_counts = duthost.shell("show ipv6 route summary | grep Total | awk '{print $2}'")["stdout"]
        logging.info("IPv6 routes at start %s", start_time_ipv6_route_counts)

        # Make Sure Orch CPU < orch_cpu_threshold before starting test.
        logging.info("Make Sure orchagent CPU utilization is less that %d before link flap", orch_cpu_threshold)
        for _ in range(100):
            orch_cpu = duthost.shell("show processes cpu | grep orchagent | awk '{print $9}'")["stdout"]
            if int(float(orch_cpu)) < orch_cpu_threshold:
                break
            time.sleep(2)
        else:
            pytest.fail("Orch CPU utilization {} > orch cpu threshold {} before link flap".format(orch_cpu, orch_cpu_threshold))

        # Flap all interfaces one by one on DUT
        for iteration in range(3):
            logging.info("%d Iteration flap all interfaces one by one on DUT", iteration + 1)
            port_toggle(duthost, watch=True)

        # Flap all interfaces one by one on Peer Device
        for iteration in range(3):
            logging.info("%d Iteration flap all interfaces one by one on Peer Device", iteration + 1)
            candidates = build_test_candidates(duthost, fanouthosts)

            if not candidates:
                pytest.skip("Didn't find any port that is admin up and present in the connection graph")

            for dut_port, fanout, fanout_port in candidates:
                toggle_one_link(duthost, dut_port, fanout, fanout_port, watch=True)

        # Wait 60 secs so that BGP routes are relearned
        time.sleep(60)

        # Record memory status at end
        memory_output = duthost.shell("show system-memory")["stdout"]
        logging.info("Memory Status at end: %s", memory_output)

        # Record orchagent CPU utilization at end
        orch_cpu = duthost.shell("show processes cpu | grep orchagent | awk '{print $9}'")["stdout"]
        logging.info("Orchagent CPU Util at end: %s", orch_cpu)

        # Record Redis Memory at end
        end_time_redis_memory = duthost.shell("redis-cli info memory | grep used_memory_human | sed -e 's/.*:\(.*\)M/\\1/'")["stdout"]
        logging.info("Redis Memory at start: %s M", start_time_redis_memory)
        logging.info("Redis Memory at end: %s M", end_time_redis_memory)

        # Calculate diff in Redis memory
        incr_redis_memory = float(end_time_redis_memory) - float(start_time_redis_memory)
        logging.info("Redis absolute  difference: %d", incr_redis_memory)

        # Check redis memory only if it is increased else default to pass
        if incr_redis_memory > 0.0:
            percent_incr_redis_memory = (incr_redis_memory / float(start_time_redis_memory)) * 100
            logging.info("Redis Memory percentage Increase: %d", percent_incr_redis_memory)
            pytest_assert(percent_incr_redis_memory < 5, "Redis Memory Increase more than expected: {}".format(percent_incr_redis_memory))

        # Record ipv4 route counts at end
        end_time_ipv4_route_counts = duthost.shell("show ip route summary | grep Total | awk '{print $2}'")["stdout"]
        logging.info("IPv4 routes at start: %s", start_time_ipv4_route_counts)
        logging.info("IPv4 routes at end: %s", end_time_ipv4_route_counts)

        # Make Sure all ipv4 routes are relearned with jitter of ~5
        incr_ipv4_route_counts = abs(int(float(start_time_ipv4_route_counts)) - int(float(end_time_ipv4_route_counts)))
        pytest_assert(incr_ipv4_route_counts < 5, "Ipv4 routes are not equal after link flap")

        end_time_ipv6_route_counts = duthost.shell("show ipv6 route summary | grep Total | awk '{print $2}'")["stdout"]
        logging.info("IPv6 routes at start: %s", start_time_ipv6_route_counts)
        logging.info("IPv6 routes at end: %s", end_time_ipv6_route_counts)

        incr_ipv6_route_counts = abs(int(float(start_time_ipv6_route_counts)) - int(float(end_time_ipv6_route_counts)))
        pytest_assert(incr_ipv6_route_counts < 5, "Ipv6 routes are not equal after link flap")

        # Wait for 15 more secs.
        time.sleep(15)

        # Orchagent CPU should consume < orch_cpu_threshold at last.
        logging.info("watch orchagent CPU utilization when it goes below %d", orch_cpu_threshold)
        for _ in range(30):
            orch_cpu = duthost.shell("show processes cpu | grep orchagent | awk '{print $9}'")["stdout"]
            if int(float(orch_cpu)) < orch_cpu_threshold:
                break
            time.sleep(2)
        else:
            pytest.fail("Orch CPU utilization {} > orch cpu threshold {} before link flap".format(orch_cpu, orch_cpu_threshold))
