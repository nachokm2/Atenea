/// Estado del Personaje: Vestidor (P16), Mercado (P15) y las modales de ítem
/// desbloqueado (P14).
///
/// Equipar es **optimista**: la ranura cambia al instante y, si el Reino
/// rechaza el cambio, se revierte con un aviso. Las capas del avatar siempre
/// las manda el servidor; aquí nunca se recomponen a mano.
library;

import 'package:flutter/foundation.dart';

import '../data/errores.dart';
import '../datos/repositorios.dart';

/// Avatar, inventario y mercado.
class ControladorPersonaje extends ChangeNotifier {
  ControladorPersonaje(this._repos);

  final Repositorios _repos;

  // --- Avatar --------------------------------------------------------------
  Avatar? _avatar;
  bool _cargandoAvatar = false;
  ErrorAtenea? _errorAvatar;
  String? _guardandoRanura;

  // --- Inventario ----------------------------------------------------------
  List<ItemInventario> _inventario = const <ItemInventario>[];
  String? _cursorInventario;
  bool _hayMasInventario = false;
  bool _cargandoInventario = false;
  bool _cargandoMasInventario = false;
  ErrorAtenea? _errorInventario;
  RanuraItem? _ranuraSeleccionada;
  RarezaItem? _filtroRareza;
  OrigenItem? _filtroOrigen;

  // --- Mercado -------------------------------------------------------------
  Tienda? _tienda;
  bool _cargandoTienda = false;
  ErrorAtenea? _errorTienda;
  RanuraItem? _categoriaMercado;
  bool _soloAlcanzables = false;
  bool _comprando = false;
  Compra? _ultimaCompra;
  final Map<String, String> _clavesCompra = <String, String>{};

  // --- Ficha (nombre y Orden) ------------------------------------------------
  bool _guardandoFicha = false;
  ErrorAtenea? _errorFicha;

  // -------------------------------------------------------------------------
  // Lecturas — avatar
  // -------------------------------------------------------------------------

  /// Avatar con rasgos, equipo y capas ya ordenadas por z.
  Avatar? get avatar => _avatar;

  /// Capas listas para pintar el muñeco.
  List<CapaAvatar> get capas => _avatar?.capas ?? const <CapaAvatar>[];

  /// Carga del avatar en curso.
  bool get cargandoAvatar => _cargandoAvatar;

  /// Error del avatar.
  ErrorAtenea? get errorAvatar => _errorAvatar;

  /// Ranura que se está guardando ahora mismo (para el indicador de P16).
  RanuraItem? get ranuraGuardando => _guardandoRanura == null
      ? null
      : desdeClaveApiOpcional(RanuraItem.values, _guardandoRanura);

  /// Instancia equipada en una ranura, o `null` si está vacía.
  String? equipadoEn(RanuraItem ranura) => _avatar?.equipadoEn(ranura);

  // -------------------------------------------------------------------------
  // Lecturas — inventario
  // -------------------------------------------------------------------------

  /// Ítems del inventario, ya filtrados por el servidor.
  List<ItemInventario> get inventario =>
      List<ItemInventario>.unmodifiable(_inventario);

  /// Ítems de la ranura seleccionada, con los poseídos primero.
  List<ItemInventario> get itemsDeLaRanura {
    final List<ItemInventario> copia = List<ItemInventario>.of(_inventario);
    copia.sort((ItemInventario a, ItemInventario b) {
      if (a.poseido != b.poseido) return a.poseido ? -1 : 1;
      return a.item.rareza.orden.compareTo(b.item.rareza.orden);
    });
    return List<ItemInventario>.unmodifiable(copia);
  }

  /// Cuántos ítems posee el usuario de los que se están mostrando.
  int get poseidos =>
      _inventario.where((ItemInventario i) => i.poseido).length;

  /// ¿Quedan más páginas de inventario?
  bool get hayMasInventario => _hayMasInventario;

  /// Primera carga del inventario.
  bool get cargandoInventario => _cargandoInventario;

  /// Trayendo más inventario.
  bool get cargandoMasInventario => _cargandoMasInventario;

  /// Error del inventario.
  ErrorAtenea? get errorInventario => _errorInventario;

  /// Ranura seleccionada en el Vestidor.
  RanuraItem? get ranuraSeleccionada => _ranuraSeleccionada;

  /// Filtro de rareza activo.
  RarezaItem? get filtroRareza => _filtroRareza;

  /// Filtro de origen activo.
  OrigenItem? get filtroOrigen => _filtroOrigen;

  // -------------------------------------------------------------------------
  // Lecturas — mercado
  // -------------------------------------------------------------------------

  /// Catálogo del Mercado.
  Tienda? get tienda => _tienda;

  /// Saldo de oro tal como lo calcula el servidor.
  int get saldo => _ultimaCompra?.saldoDespues ?? _tienda?.saldo ?? 0;

  /// Carga del Mercado en curso.
  bool get cargandoTienda => _cargandoTienda;

  /// Error del Mercado.
  ErrorAtenea? get errorTienda => _errorTienda;

  /// Categoría elegida en los chips del Mercado.
  RanuraItem? get categoriaMercado => _categoriaMercado;

  /// ¿Está activo el filtro "Puedo comprar"?
  bool get soloAlcanzables => _soloAlcanzables;

  /// ¿Hay una compra en vuelo?
  bool get comprando => _comprando;

  /// Última compra ejecutada, para la animación de monedas y el CTA "Equipar".
  Compra? get ultimaCompra => _ultimaCompra;

  /// Anuncios visibles según los filtros de P15.
  List<Anuncio> get anunciosVisibles {
    final Tienda? catalogo = _tienda;
    if (catalogo == null) return const <Anuncio>[];
    Iterable<Anuncio> lista = catalogo.anuncios;
    final RanuraItem? categoria = _categoriaMercado;
    if (categoria != null) {
      lista = lista.where((Anuncio a) => a.item.ranura == categoria);
    }
    if (_soloAlcanzables) {
      lista = lista.where(
        (Anuncio a) => a.puedeComprar && a.puedePagar && !a.poseido,
      );
    }
    return List<Anuncio>.unmodifiable(lista);
  }

  /// Ítems que no se compran: se ganan aprendiendo.
  List<Anuncio> get itemsDeConocimiento =>
      _tienda?.itemsDeConocimiento ?? const <Anuncio>[];

  // -------------------------------------------------------------------------
  // Lecturas — ficha
  // -------------------------------------------------------------------------

  /// Guardando un cambio de nombre u Orden.
  bool get guardandoFicha => _guardandoFicha;

  /// Error de la ficha (nombre u Orden).
  ErrorAtenea? get errorFicha => _errorFicha;

  // -------------------------------------------------------------------------
  // Avatar
  // -------------------------------------------------------------------------

  /// Renombra el personaje o le cambia la Orden (gratis en el MVP, §7.2).
  ///
  /// Devuelve el [Personaje] ya actualizado para que quien llama lo reparta a
  /// `ControladorSesion` y refresque el Perfil: esta clase no guarda su propia
  /// copia porque no es quien la muestra.
  Future<Personaje?> actualizarFicha({String? nombre, Arquetipo? arquetipo}) async {
    _guardandoFicha = true;
    _errorFicha = null;
    notifyListeners();
    try {
      final Personaje actualizado = await _repos.personaje.actualizar(
        nombre: nombre,
        arquetipo: arquetipo,
      );
      return actualizado;
    } catch (e) {
      _errorFicha = _comoError(e);
      return null;
    } finally {
      _guardandoFicha = false;
      notifyListeners();
    }
  }

  /// Trae el avatar y su manifiesto de capas.
  Future<void> cargarAvatar({bool forzar = false}) async {
    if (_cargandoAvatar) return;
    if (!forzar && _avatar != null) return;
    _cargandoAvatar = true;
    _errorAvatar = null;
    notifyListeners();
    try {
      _avatar = await _repos.personaje.avatar();
    } catch (e) {
      _errorAvatar = _comoError(e);
    } finally {
      _cargandoAvatar = false;
      notifyListeners();
    }
  }

  /// Cambia rasgos gratuitos (piel, rostro, orejas, cabello, trato).
  Future<bool> cambiarRasgos({
    TipoCuerpo? tipoCuerpo,
    String? tonoPiel,
    String? rostro,
    String? orejas,
    String? cabello,
    String? colorCabello,
    FormaTrato? formaTrato,
    String? colorAcento,
  }) async {
    final Avatar? anterior = _avatar;
    try {
      _avatar = await _repos.personaje.cambiarRasgos(
        tipoCuerpo: tipoCuerpo,
        tonoPiel: tonoPiel,
        rostro: rostro,
        orejas: orejas,
        cabello: cabello,
        colorCabello: colorCabello,
        formaTrato: formaTrato,
        colorAcento: colorAcento,
      );
      _errorAvatar = null;
      notifyListeners();
      return true;
    } catch (e) {
      _avatar = anterior;
      _errorAvatar = _comoError(e);
      notifyListeners();
      return false;
    }
  }

  /// Equipa un ítem poseído en su ranura, con actualización optimista.
  Future<bool> equipar(ItemInventario item) async {
    final String? instancia = item.itemUsuarioId;
    if (instancia == null) return false;
    return _guardarEquipo(item.item.ranura, instancia);
  }

  /// Deja la ranura vacía, con actualización optimista.
  Future<bool> desequipar(RanuraItem ranura) => _guardarEquipo(ranura, null);

  Future<bool> _guardarEquipo(RanuraItem ranura, String? instancia) async {
    final Avatar? anterior = _avatar;
    if (anterior == null) return false;

    // Optimista: la selección cambia ya. Las capas siguen siendo las del
    // servidor hasta que responda, porque el cliente no las recompone.
    _avatar = Avatar(
      rasgos: anterior.rasgos,
      arquetipo: anterior.arquetipo,
      equipo: anterior.equipoCon(ranura, instancia),
      capas: anterior.capas,
      etiquetaVersion: anterior.etiquetaVersion,
    );
    _inventario = _conEquipado(ranura, instancia);
    _guardandoRanura = ranura.api;
    _errorAvatar = null;
    notifyListeners();

    try {
      _avatar = await _repos.personaje.cambiarEquipo(
        <RanuraItem, String?>{ranura: instancia},
      );
      _inventario = _conEquipado(ranura, instancia);
      return true;
    } catch (e) {
      // Reversión visual con aviso (§P16, estado "error de guardado").
      _avatar = anterior;
      _inventario = _conEquipado(ranura, anterior.equipadoEn(ranura));
      _errorAvatar = _comoError(e);
      return false;
    } finally {
      _guardandoRanura = null;
      notifyListeners();
    }
  }

  List<ItemInventario> _conEquipado(RanuraItem ranura, String? instancia) {
    return <ItemInventario>[
      for (final ItemInventario i in _inventario)
        if (i.item.ranura != ranura)
          i
        else
          ItemInventario(
            item: i.item,
            itemUsuarioId: i.itemUsuarioId,
            poseido: i.poseido,
            esNuevo: i.esNuevo,
            equipado: instancia != null && i.itemUsuarioId == instancia,
            requisitos: i.requisitos,
            adquiridoEn: i.adquiridoEn,
            motivoDesbloqueo: i.motivoDesbloqueo,
            puedeEquipar: i.puedeEquipar,
          ),
    ];
  }

  // -------------------------------------------------------------------------
  // Inventario
  // -------------------------------------------------------------------------

  /// Selecciona la ranura del Vestidor y recarga su bandeja.
  Future<void> seleccionarRanura(RanuraItem? ranura) async {
    if (_ranuraSeleccionada == ranura) return;
    _ranuraSeleccionada = ranura;
    notifyListeners();
    await cargarInventario(forzar: true);
  }

  /// Cambia los filtros de rareza y origen.
  Future<void> filtrar({
    RarezaItem? rareza,
    OrigenItem? origen,
    bool limpiarRareza = false,
    bool limpiarOrigen = false,
  }) async {
    _filtroRareza = limpiarRareza ? null : (rareza ?? _filtroRareza);
    _filtroOrigen = limpiarOrigen ? null : (origen ?? _filtroOrigen);
    notifyListeners();
    await cargarInventario(forzar: true);
  }

  /// Trae la primera página del inventario con los filtros vigentes.
  Future<void> cargarInventario({bool forzar = false}) async {
    if (_cargandoInventario) return;
    if (!forzar && _inventario.isNotEmpty) return;
    _cargandoInventario = true;
    _errorInventario = null;
    notifyListeners();
    try {
      final Pagina<ItemInventario> pagina = await _repos.inventario.inventario(
        ranura: _ranuraSeleccionada,
        rareza: _filtroRareza,
        origen: _filtroOrigen,
      );
      _inventario = pagina.elementos;
      _cursorInventario = pagina.cursorSiguiente;
      _hayMasInventario = pagina.info.puedeSeguir;
    } catch (e) {
      _errorInventario = _comoError(e);
    } finally {
      _cargandoInventario = false;
      notifyListeners();
    }
  }

  /// Trae la siguiente página del inventario.
  Future<void> masInventario() async {
    final String? cursor = _cursorInventario;
    if (_cargandoMasInventario || !_hayMasInventario || cursor == null) return;
    _cargandoMasInventario = true;
    notifyListeners();
    try {
      final Pagina<ItemInventario> pagina = await _repos.inventario.inventario(
        ranura: _ranuraSeleccionada,
        rareza: _filtroRareza,
        origen: _filtroOrigen,
        cursor: cursor,
      );
      _inventario = <ItemInventario>[..._inventario, ...pagina.elementos];
      _cursorInventario = pagina.cursorSiguiente;
      _hayMasInventario = pagina.info.puedeSeguir;
    } catch (e) {
      _errorInventario = _comoError(e);
    } finally {
      _cargandoMasInventario = false;
      notifyListeners();
    }
  }

  /// Ficha completa de un ítem, para la hoja inferior.
  Future<DetalleItem?> ficha(String itemId) async {
    try {
      return await _repos.inventario.item(itemId);
    } catch (e) {
      _errorInventario = _comoError(e);
      notifyListeners();
      return null;
    }
  }

  /// Registra que el usuario probó un ítem en la vista previa (métrica).
  Future<void> registrarPrueba(String itemId) async {
    try {
      await _repos.inventario.registrarPrueba(itemId);
    } catch (_) {
      // Es telemetría: un fallo no se le cuenta al usuario.
    }
  }

  // -------------------------------------------------------------------------
  // Mercado
  // -------------------------------------------------------------------------

  /// Trae el catálogo con el saldo vigente.
  Future<void> cargarTienda({bool forzar = false}) async {
    if (_cargandoTienda) return;
    if (!forzar && _tienda != null) return;
    _cargandoTienda = true;
    _errorTienda = null;
    notifyListeners();
    try {
      _tienda = await _repos.tienda.tienda();
    } catch (e) {
      _errorTienda = _comoError(e);
    } finally {
      _cargandoTienda = false;
      notifyListeners();
    }
  }

  /// Chip de categoría del Mercado.
  void fijarCategoria(RanuraItem? ranura) {
    if (_categoriaMercado == ranura) return;
    _categoriaMercado = ranura;
    notifyListeners();
  }

  /// Filtro "Puedo comprar".
  void alternarAlcanzables() {
    _soloAlcanzables = !_soloAlcanzables;
    notifyListeners();
  }

  /// Compra un anuncio al precio que muestra la pantalla.
  ///
  /// El precio viaja como `precioEsperado` para que el servidor rechace la
  /// compra si cambió mientras el usuario decidía.
  Future<Compra?> comprar(Anuncio anuncio) async {
    if (_comprando) return null;
    _comprando = true;
    _errorTienda = null;
    notifyListeners();
    final String clave = _clavesCompra.putIfAbsent(
      anuncio.id,
      () => claveIdempotencia(),
    );
    try {
      final Compra compra = await _repos.tienda.comprar(
        anuncioId: anuncio.id,
        precioEsperado: anuncio.precio,
        clave: clave,
      );
      _ultimaCompra = compra;
      _clavesCompra.remove(anuncio.id);
      if (compra.capasAvatar.isNotEmpty) {
        final Avatar? actual = _avatar;
        if (actual != null) {
          _avatar = Avatar(
            rasgos: actual.rasgos,
            arquetipo: actual.arquetipo,
            equipo: actual.equipo,
            capas: compra.capasAvatar,
            etiquetaVersion: actual.etiquetaVersion,
          );
        }
      }
      await cargarTienda(forzar: true);
      await cargarInventario(forzar: true);
      return compra;
    } catch (e) {
      _errorTienda = _comoError(e);
      return null;
    } finally {
      _comprando = false;
      notifyListeners();
    }
  }

  /// Deshace una compra reciente dentro de la ventana de gracia.
  Future<bool> deshacerCompra(String compraId) async {
    try {
      final Compra deshecha = await _repos.tienda.deshacerCompra(compraId);
      _ultimaCompra = deshecha;
      await cargarTienda(forzar: true);
      await cargarInventario(forzar: true);
      return true;
    } catch (e) {
      _errorTienda = _comoError(e);
      notifyListeners();
      return false;
    }
  }

  /// Movimientos de oro, para el detalle del monedero.
  Future<Monedero?> monedero() async {
    try {
      return await _repos.tienda.monedero();
    } catch (e) {
      _errorTienda = _comoError(e);
      notifyListeners();
      return null;
    }
  }

  /// Olvida la última compra tras mostrar su animación.
  void olvidarCompra() {
    if (_ultimaCompra == null) return;
    _ultimaCompra = null;
    notifyListeners();
  }

  /// Borra los errores visibles.
  void limpiarErrores() {
    if (_errorAvatar == null && _errorInventario == null && _errorTienda == null) {
      return;
    }
    _errorAvatar = null;
    _errorInventario = null;
    _errorTienda = null;
    notifyListeners();
  }

  /// Olvida todo al cerrar sesión.
  void limpiar() {
    _avatar = null;
    _inventario = const <ItemInventario>[];
    _cursorInventario = null;
    _hayMasInventario = false;
    _tienda = null;
    _ultimaCompra = null;
    _clavesCompra.clear();
    _ranuraSeleccionada = null;
    _filtroRareza = null;
    _filtroOrigen = null;
    _categoriaMercado = null;
    _soloAlcanzables = false;
    _errorAvatar = null;
    _errorInventario = null;
    _errorTienda = null;
    notifyListeners();
  }
}

/// Traduce cualquier fallo a un [ErrorAtenea] con mensaje en español.
ErrorAtenea _comoError(Object error) => error is ErrorAtenea
    ? error
    : const ErrorAtenea(
        codigo: 'inesperado',
        mensaje: 'Ocurrió algo inesperado. Inténtalo de nuevo.',
      );
