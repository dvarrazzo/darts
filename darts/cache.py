from functools import wraps

def cached(f):
	"""Evaluate a function call only once.

	The function should be called using only positional arguments. All the
	parameters should be hashable.

	The decorator is not thread-safe. If needed use the `synchro` decorator
	to serialize access to the function.
	"""
	return cached_in({})(f)

def cached_in(cache):
	"""Evaluate a function call only once.

	Use an external dictionary as cache: this allows interaction with the cache
	from other functions.
	"""
	def cached_in_(f):
		@wraps(f)
		def cached_in__(*args):
			try:
				return cache[args]
			except KeyError:
				cache[args] = f(*args)
				return cache[args]

		return cached_in__
	return cached_in_

def cached_method(f):
	"""Evaluate a method call only once. Results are cached per class instance.

	The method should be called using only positional arguments. All the
	parameters should be hashable.

	The decorator is not thread-safe. If needed use the `synchro_method`
	decorator to serialize access to the function.
	"""
	cache_name = "_cache_%s" % f.__name__
	@wraps(f)
	def cached_method_(self, *args):
		try:
			cache = getattr(self, cache_name)
		except AttributeError:
			cache = {}
			setattr(self, cache_name, cache)

		try:
			return cache[args]
		except KeyError:
			cache[args] = f(self, *args)
			return cache[args]

	return cached_method_


