"""定长环形缓冲。

设计约束（对应设计文档 §7）：

* 采集回调线程只做 ``write``，绝不在这里做重活；
* 分析线程按固定块长 ``read``；
* 容量固定，长跑不增长；溢出时丢弃**最旧**数据并计数，而不是阻塞采集。

单写单读 + 一把锁保护游标，临界区只做内存拷贝，不开销。
"""

from __future__ import annotations

import threading

import numpy as np


class RingBuffer:
    """定长环形样本缓冲。"""

    def __init__(self, capacity: int, dtype: np.dtype = np.float32) -> None:
        if capacity <= 0:
            raise ValueError(f"capacity 必须为正，收到 {capacity}")
        self._buf = np.zeros(capacity, dtype=dtype)
        self._capacity = int(capacity)
        self._write = 0
        self._read = 0
        self._available = 0
        self._overflows = 0
        self._dropped = 0
        self._lock = threading.Lock()

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def available(self) -> int:
        with self._lock:
            return self._available

    @property
    def free(self) -> int:
        with self._lock:
            return self._capacity - self._available

    @property
    def fill_ratio(self) -> float:
        return self.available / self._capacity

    @property
    def overflows(self) -> int:
        """发生溢出的次数。"""
        with self._lock:
            return self._overflows

    @property
    def dropped_samples(self) -> int:
        """累计被丢弃的样本数。"""
        with self._lock:
            return self._dropped

    def write(self, samples: np.ndarray) -> int:
        """写入样本，返回实际写入数量。空间不足时丢弃最旧数据。"""
        data = np.asarray(samples, dtype=self._buf.dtype).ravel()
        n = int(data.size)
        if n == 0:
            return 0
        if n > self._capacity:
            # 单次写入超过整个容量：只保留最后 capacity 个样本
            data = data[-self._capacity :]
            n = self._capacity

        with self._lock:
            free = self._capacity - self._available
            if n > free:
                drop = n - free
                self._overflows += 1
                self._dropped += drop
                self._read = (self._read + drop) % self._capacity
                self._available -= drop

            first = min(n, self._capacity - self._write)
            self._buf[self._write : self._write + first] = data[:first]
            rest = n - first
            if rest:
                self._buf[:rest] = data[first:]
            self._write = (self._write + n) % self._capacity
            self._available += n
        return n

    def read(self, n: int) -> np.ndarray:
        """读取至多 n 个样本；不足时返回实际可读数量。"""
        if n <= 0:
            return np.empty(0, dtype=self._buf.dtype)
        with self._lock:
            take = min(n, self._available)
            if take == 0:
                return np.empty(0, dtype=self._buf.dtype)
            out = np.empty(take, dtype=self._buf.dtype)
            first = min(take, self._capacity - self._read)
            out[:first] = self._buf[self._read : self._read + first]
            rest = take - first
            if rest:
                out[first:] = self._buf[:rest]
            self._read = (self._read + take) % self._capacity
            self._available -= take
        return out

    def drain(self) -> np.ndarray:
        """读出全部可读样本。"""
        return self.read(self.available)

    def clear(self) -> None:
        with self._lock:
            self._read = 0
            self._write = 0
            self._available = 0
            self._buf.fill(0)
