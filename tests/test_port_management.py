from rugby_sim.webapp import _parse_listening_pids

SAMPLE_NETSTAT_OUTPUT = """
Active Connections

  Proto  Local Address          Foreign Address        State           PID
  TCP    0.0.0.0:135            0.0.0.0:0              LISTENING       812
  TCP    127.0.0.1:5000         0.0.0.0:0              LISTENING       4321
  TCP    0.0.0.0:5001           0.0.0.0:0              LISTENING       7777
  TCP    127.0.0.1:5000         127.0.0.1:52344        ESTABLISHED     4321
  TCP    0.0.0.0:49668          0.0.0.0:0              LISTENING       0
"""


def test_finds_pid_listening_on_the_target_port():
    assert _parse_listening_pids(SAMPLE_NETSTAT_OUTPUT, 5000) == {"4321"}


def test_ignores_established_connections_and_other_ports():
    pids = _parse_listening_pids(SAMPLE_NETSTAT_OUTPUT, 5001)
    assert pids == {"7777"}


def test_ignores_pid_zero_and_unrelated_ports():
    assert _parse_listening_pids(SAMPLE_NETSTAT_OUTPUT, 9999) == set()


def test_empty_output_returns_no_pids():
    assert _parse_listening_pids("", 5000) == set()
