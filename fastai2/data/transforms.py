# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/05_data.transforms.ipynb (unless otherwise specified).

__all__ = ['get_files', 'FileGetter', 'image_extensions', 'get_image_files', 'ImageGetter', 'get_text_files',
           'RandomSplitter', 'IndexSplitter', 'GrandparentSplitter', 'FuncSplitter', 'MaskSplitter', 'FileSplitter',
           'ColSplitter', 'parent_label', 'RegexLabeller', 'ColReader', 'CategoryMap', 'Categorize', 'Category',
           'MultiCategorize', 'MultiCategory', 'OneHotEncode', 'EncodedMultiCategorize', 'get_c', 'ToTensor', 'Cuda',
           'IntToFloatTensor', 'broadcast_vec', 'Normalize']

# Cell
from ..torch_basics import *
from .core import *
from .load import *
from .external import *

# Cell
def _get_files(p, fs, extensions=None):
    p = Path(p)
    res = [p/f for f in fs if not f.startswith('.')
           and ((not extensions) or f'.{f.split(".")[-1].lower()}' in extensions)]
    return res

# Cell
def get_files(path, extensions=None, recurse=True, folders=None):
    "Get all the files in `path` with optional `extensions`, optionally with `recurse`, only in `folders`, if specified."
    path = Path(path)
    folders=L(folders)
    extensions = setify(extensions)
    extensions = {e.lower() for e in extensions}
    if recurse:
        res = []
        for i,(p,d,f) in enumerate(os.walk(path)): # returns (dirpath, dirnames, filenames)
            if len(folders) !=0 and i==0: d[:] = [o for o in d if o in folders]
            else:                         d[:] = [o for o in d if not o.startswith('.')]
            res += _get_files(p, f, extensions)
    else:
        f = [o.name for o in os.scandir(path) if o.is_file()]
        res = _get_files(path, f, extensions)
    return L(res)

# Cell
def FileGetter(suf='', extensions=None, recurse=True, folders=None):
    "Create `get_files` partial function that searches path suffix `suf`, only in `folders`, if specified, and passes along args"
    def _inner(o, extensions=extensions, recurse=recurse, folders=folders):
        return get_files(o/suf, extensions, recurse, folders)
    return _inner

# Cell
image_extensions = set(k for k,v in mimetypes.types_map.items() if v.startswith('image/'))

# Cell
def get_image_files(path, recurse=True, folders=None):
    "Get image files in `path` recursively, only in `folders`, if specified."
    return get_files(path, extensions=image_extensions, recurse=recurse, folders=folders)

# Cell
def ImageGetter(suf='', recurse=True, folders=None):
    "Create `get_image_files` partial function that searches path suffix `suf` and passes along `kwargs`, only in `folders`, if specified."
    def _inner(o, recurse=recurse, folders=folders): return get_image_files(o/suf, recurse, folders)
    return _inner

# Cell
def get_text_files(path, recurse=True, folders=None):
    "Get text files in `path` recursively, only in `folders`, if specified."
    return get_files(path, extensions=['.txt'], recurse=recurse, folders=folders)

# Cell
def RandomSplitter(valid_pct=0.2, seed=None, **kwargs):
    "Create function that splits `items` between train/val with `valid_pct` randomly."
    def _inner(o, **kwargs):
        if seed is not None: torch.manual_seed(seed)
        rand_idx = L(int(i) for i in torch.randperm(len(o)))
        cut = int(valid_pct * len(o))
        return rand_idx[cut:],rand_idx[:cut]
    return _inner

# Cell
def IndexSplitter(valid_idx):
    "Split `items` so that `val_idx` are in the validation set and the others in the training set"
    def _inner(o, **kwargs):
        train_idx = np.setdiff1d(np.array(range_of(o)), np.array(valid_idx))
        return L(train_idx, use_list=True), L(valid_idx, use_list=True)
    return _inner

# Cell
def _grandparent_idxs(items, name): return mask2idxs(Path(o).parent.parent.name == name for o in items)

# Cell
def GrandparentSplitter(train_name='train', valid_name='valid'):
    "Split `items` from the grand parent folder names (`train_name` and `valid_name`)."
    def _inner(o, **kwargs):
        return _grandparent_idxs(o, train_name),_grandparent_idxs(o, valid_name)
    return _inner

# Cell
def FuncSplitter(func):
    "Split `items` by result of `func` (`True` for validation, `False` for training set)."
    def _inner(o, **kwargs):
        val_idx = mask2idxs(func(o_) for o_ in o)
        return IndexSplitter(val_idx)(o)
    return _inner

# Cell
def MaskSplitter(mask):
    "Split `items` depending on the value of `mask`."
    def _inner(o, **kwargs): return IndexSplitter(mask2idxs(mask))(o)
    return _inner

# Cell
def FileSplitter(fname):
    "Split `items` depending on the value of `mask`."
    valid = Path(fname).read().split('\n')
    def _func(x): return x.name in valid
    def _inner(o, **kwargs): return FuncSplitter(_func)(o)
    return _inner

# Cell
def ColSplitter(col='is_valid'):
    "Split `items` (supposed to be a dataframe) by value in `col`"
    def _inner(o, **kwargs):
        assert isinstance(o, pd.DataFrame), "ColSplitter only works when your items are a pandas DataFrame"
        valid_idx = o[col].values
        return IndexSplitter(mask2idxs(valid_idx))(o)
    return _inner

# Cell
def parent_label(o, **kwargs):
    "Label `item` with the parent folder name."
    return Path(o).parent.name

# Cell
class RegexLabeller():
    "Label `item` with regex `pat`."
    def __init__(self, pat, match=False):
        self.pat = re.compile(pat)
        self.matcher = self.pat.match if match else self.pat.search

    def __call__(self, o, **kwargs):
        res = self.matcher(str(o))
        assert res,f'Failed to find "{self.pat}" in "{o}"'
        return res.group(1)

# Cell
class ColReader():
    "Read `cols` in `row` with potential `pref` and `suff`"
    def __init__(self, cols, pref='', suff='', label_delim=None):
        store_attr(self, 'suff,label_delim')
        self.pref = str(pref) + os.path.sep if isinstance(pref, Path) else pref
        self.cols = L(cols)

    def _do_one(self, r, c):
        o = r[c] if isinstance(c, int) else getattr(r, c)
        if len(self.pref)==0 and len(self.suff)==0 and self.label_delim is None: return o
        if self.label_delim is None: return f'{self.pref}{o}{self.suff}'
        else: return o.split(self.label_delim) if len(o)>0 else []

    def __call__(self, o, **kwargs): return detuplify(tuple(self._do_one(o, c) for c in self.cols))

# Cell
class CategoryMap(CollBase):
    "Collection of categories with the reverse mapping in `o2i`"
    def __init__(self, col, sort=True, add_na=False):
        if is_categorical_dtype(col): items = L(col.cat.categories, use_list=True)
        else:
            if not hasattr(col,'unique'): col = L(col, use_list=True)
            # `o==o` is the generalized definition of non-NaN used by Pandas
            items = L(o for o in col.unique() if o==o)
            if sort: items = items.sorted()
        self.items = '#na#' + items if add_na else items
        self.o2i = defaultdict(int, self.items.val2idx()) if add_na else dict(self.items.val2idx())
    def __eq__(self,b): return all_equal(b,self)

# Cell
class Categorize(Transform):
    "Reversible transform of category string to `vocab` id"
    loss_func,order=CrossEntropyLossFlat(),1
    def __init__(self, vocab=None, add_na=False):
        self.add_na = add_na
        self.vocab = None if vocab is None else CategoryMap(vocab, add_na=add_na)

    def setups(self, dsrc):
        if self.vocab is None and dsrc is not None: self.vocab = CategoryMap(dsrc, add_na=self.add_na)
        self.c = len(self.vocab)

    def encodes(self, o): return TensorCategory(self.vocab.o2i[o])
    def decodes(self, o): return Category      (self.vocab    [o])

# Cell
class Category(str, ShowTitle): _show_args = {'label': 'category'}

# Cell
class MultiCategorize(Categorize):
    "Reversible transform of multi-category strings to `vocab` id"
    loss_func,order=BCEWithLogitsLossFlat(),1
    def __init__(self, vocab=None, add_na=False):
        self.add_na = add_na
        self.vocab = None if vocab is None else CategoryMap(vocab, add_na=add_na)

    def setups(self, dsrc):
        if not dsrc: return
        if self.vocab is None:
            vals = set()
            for b in dsrc: vals = vals.union(set(b))
            self.vocab = CategoryMap(list(vals), add_na=self.add_na)

    def encodes(self, o): return TensorMultiCategory([self.vocab.o2i[o_] for o_ in o])
    def decodes(self, o): return MultiCategory      ([self.vocab    [o_] for o_ in o])

# Cell
class MultiCategory(L):
    def show(self, ctx=None, sep=';', color='black', **kwargs):
        return show_title(sep.join(self.map(str)), ctx=ctx, color=color, **kwargs)

# Cell
class OneHotEncode(Transform):
    "One-hot encodes targets"
    order=2
    def __init__(self, c=None): self.c = c

    def setups(self, dsrc):
        if self.c is None: self.c = len(L(getattr(dsrc, 'vocab', None)))
        if not self.c: warn("Couldn't infer the number of classes, please pass a value for `c` at init")

    def encodes(self, o): return TensorMultiCategory(one_hot(o, self.c).float())
    def decodes(self, o): return one_hot_decode(o, None)

# Cell
class EncodedMultiCategorize(Categorize):
    "Transform of one-hot encoded multi-category that decodes with `vocab`"
    loss_func,order=BCEWithLogitsLossFlat(),1
    def __init__(self, vocab): self.vocab,self.c = vocab,len(vocab)
    def encodes(self, o): return TensorCategory(tensor(o).float())
    def decodes(self, o): return MultiCategory (one_hot_decode(o, self.vocab))

# Cell
def get_c(dbunch):
    if getattr(dbunch, 'c', False): return dbunch.c
    vocab = getattr(dbunch, 'vocab', [])
    if len(vocab) > 0 and is_listy(vocab[-1]): vocab = vocab[-1]
    return len(vocab)

# Cell
class ToTensor(Transform):
    "Convert item to appropriate tensor class"
    order = 15

# Cell
@docs
class Cuda(Transform):
    "Move batch to `device` (defaults to `default_device()`)"
    def __init__(self,device=None):
        self.device=default_device() if device is None else device
        super().__init__(split_idx=None, as_item=False)
    def encodes(self, b): return to_device(b, self.device)
    def decodes(self, b): return to_cpu(b)

    _docs=dict(encodes="Move batch to `device`", decodes="Return batch to CPU")

# Cell
class IntToFloatTensor(Transform):
    "Transform image to float tensor, optionally dividing by 255 (e.g. for images)."
    order = 20 #Need to run after CUDA if on the GPU
    def __init__(self, div=255., div_mask=1, split_idx=None, as_item=True):
        super().__init__(split_idx=split_idx,as_item=as_item)
        self.div,self.div_mask = div,div_mask

    def encodes(self, o:TensorImage): return o.float().div_(self.div)
    def encodes(self, o:TensorMask ): return o.div_(self.div_mask).long()
    def decodes(self, o:TensorImage): return o.clamp(0., 1.) if self.div else o

# Cell
def broadcast_vec(dim, ndim, *t, cuda=True):
    "Make a vector broadcastable over `dim` (out of `ndim` total) by prepending and appending unit axes"
    v = [1]*ndim
    v[dim] = -1
    f = to_device if cuda else noop
    return [f(tensor(o).view(*v)) for o in t]

# Cell
@docs
class Normalize(Transform):
    "Normalize/denorm batch of `TensorImage`"
    order=99
    def __init__(self, mean=None, std=None, axes=(0,2,3)): self.mean,self.std,self.axes = mean,std,axes

    @classmethod
    def from_stats(cls, mean, std, dim=1, ndim=4, cuda=True): return cls(*broadcast_vec(dim, ndim, mean, std, cuda=cuda))

    def setups(self, dl:DataLoader):
        if self.mean is None or self.std is None:
            x,*_ = dl.one_batch()
            self.mean,self.std = x.mean(self.axes, keepdim=True),x.std(self.axes, keepdim=True)+1e-7

    def encodes(self, x:TensorImage): return (x-self.mean) / self.std
    def decodes(self, x:TensorImage):
        f = to_cpu if x.device.type=='cpu' else noop
        return (x*f(self.std) + f(self.mean))

    _docs=dict(encodes="Normalize batch", decodes="Denormalize batch")